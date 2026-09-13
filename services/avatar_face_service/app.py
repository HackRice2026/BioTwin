from __future__ import annotations

import asyncio
import json
import logging
import math
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("avatar_face_service")

app = FastAPI(title="BioTwin Avatar Face Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_RATE = 16000
MODEL_ID = "facebook/wav2vec2-base-960h"

# Populated by load_model() at startup. Left None (and the service falls back
# to the procedural heuristic below) if torch/transformers aren't installed,
# there's no GPU, or the model fails to load for any reason -- this service
# must still come up and be useful even without the real model.
_model = None
_processor = None
_device = "cpu"


def load_model() -> None:
    global _model, _processor, _device
    try:
        import torch
        from transformers import Wav2Vec2ForCTC, Wav2Vec2Processor
    except ImportError:
        log.warning("torch/transformers not installed -- serving procedural fallback only")
        return
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        _processor = Wav2Vec2Processor.from_pretrained(MODEL_ID)
        _model = Wav2Vec2ForCTC.from_pretrained(MODEL_ID).to(_device).eval()
        log.info("loaded %s on %s", MODEL_ID, _device)
    except Exception:
        log.exception("failed to load %s -- serving procedural fallback only", MODEL_ID)
        _model = None
        _processor = None


@app.on_event("startup")
def _startup() -> None:
    load_model()


@dataclass
class Metrics:
    frames: int = 0
    inference_ms: deque[float] = field(default_factory=lambda: deque(maxlen=180))
    audio_buffer_ms: float = 0.0
    started_at: float = field(default_factory=time.perf_counter)

    @property
    def fps(self) -> float:
        elapsed = max(0.001, time.perf_counter() - self.started_at)
        return self.frames / elapsed

    @property
    def avg_inference_ms(self) -> float:
        if not self.inference_ms:
            return 0.0
        return sum(self.inference_ms) / len(self.inference_ms)


metrics = Metrics()


def gpu_snapshot() -> dict[str, Any]:
    try:
        output = subprocess.check_output(
            [
                "nvidia-smi",
                "--query-gpu=name,utilization.gpu,memory.used",
                "--format=csv,noheader,nounits",
            ],
            text=True,
            timeout=2,
        )
    except Exception:
        return {"gpu": "unavailable", "gpu_utilization": 0, "vram_mb": 0}
    first = output.strip().splitlines()[0].split(",")
    if len(first) < 3:
        return {"gpu": output.strip() or "unknown", "gpu_utilization": 0, "vram_mb": 0}
    return {
        "gpu": first[0].strip(),
        "gpu_utilization": int(first[1].strip() or 0),
        "vram_mb": int(first[2].strip() or 0),
    }


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        **gpu_snapshot(),
        "model_loaded": _model is not None,
        "backend": f"asr_viseme:{MODEL_ID}" if _model is not None else "procedural_audio_fallback",
    }


@app.get("/metrics")
def get_metrics() -> dict[str, Any]:
    gpu = gpu_snapshot()
    return {
        "fps": round(metrics.fps, 2),
        "avg_inference_ms": round(metrics.avg_inference_ms, 3),
        "audio_buffer_ms": round(metrics.audio_buffer_ms, 1),
        "gpu_utilization": gpu["gpu_utilization"],
        "vram_mb": gpu["vram_mb"],
        "model_loaded": _model is not None,
    }


def chunk_energy(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    # MP3 bytes are compressed, so this is not true PCM RMS. It is a fast,
    # deterministic envelope proxy, used only for the no-model fallback path
    # and to gate near-silence when the real model IS driving visemes.
    sample = chunk[: min(len(chunk), 4096)]
    mean = sum(abs(byte - 128) for byte in sample) / len(sample)
    return max(0.0, min(1.0, mean / 82.0))


# A small set of distinct viseme-like mouth shapes. The no-model fallback
# cycles through these blindly (see make_frame); the real model picks one of
# these per recognized character instead of cycling (see CHAR_TO_VISEME).
VISEMES: list[dict[str, float]] = [
    {"jawOpen": 0.05, "mouthClose": 0.35, "mouthFunnel": 0.0, "mouthPucker": 0.0,
     "mouthStretchLeft": 0.0, "mouthStretchRight": 0.0, "mouthSmileLeft": 0.05, "mouthSmileRight": 0.05},
    {"jawOpen": 0.55, "mouthClose": 0.0, "mouthFunnel": 0.0, "mouthPucker": 0.0,
     "mouthStretchLeft": 0.05, "mouthStretchRight": 0.05, "mouthSmileLeft": 0.1, "mouthSmileRight": 0.1},
    {"jawOpen": 0.15, "mouthClose": 0.0, "mouthFunnel": 0.0, "mouthPucker": 0.0,
     "mouthStretchLeft": 0.42, "mouthStretchRight": 0.42, "mouthSmileLeft": 0.3, "mouthSmileRight": 0.3},
    {"jawOpen": 0.25, "mouthClose": 0.0, "mouthFunnel": 0.55, "mouthPucker": 0.35,
     "mouthStretchLeft": 0.0, "mouthStretchRight": 0.0, "mouthSmileLeft": 0.0, "mouthSmileRight": 0.0},
    {"jawOpen": 0.35, "mouthClose": 0.05, "mouthFunnel": 0.1, "mouthPucker": 0.0,
     "mouthStretchLeft": 0.12, "mouthStretchRight": 0.12, "mouthSmileLeft": 0.12, "mouthSmileRight": 0.12},
]
CLOSED, OPEN_AH, WIDE_EE, ROUND_OO, MID = 0, 1, 2, 3, 4

# facebook/wav2vec2-base-960h's CTC vocab is english letters + "'" + the "|"
# word-delimiter + pad/unk/bos/eos -- there is no phoneme model here, so this
# is a simplification (a recognized LETTER selects a mouth shape, not a true
# phoneme-to-viseme mapping a real Audio2Face pipeline would use), but it is
# driven by what was actually said, not a blind timer.
_VOWEL_OPEN = set("A")
_VOWEL_WIDE = set("EIY")
_VOWEL_ROUND = set("OU")
_CLOSERS = set("BMP")  # bilabial -- lips together
_FUNNEL = set("FVW")  # labiodental / rounded-approximant -- lips forward


def char_to_viseme(ch: str) -> int:
    if ch in _VOWEL_OPEN:
        return OPEN_AH
    if ch in _VOWEL_WIDE:
        return WIDE_EE
    if ch in _VOWEL_ROUND or ch in _FUNNEL:
        return ROUND_OO
    if ch in _CLOSERS or ch in ("|", " ", "<pad>", ""):
        return CLOSED
    return MID


def make_frame(
    timestamp_ms: int, energy: float, phase: float, target_viseme: int | None
) -> dict[str, Any]:
    if target_viseme is None:
        # No model output ready yet for this stretch of audio (buffer still
        # filling, or the model isn't loaded at all) -- cycle through shapes
        # instead of freezing on one, same as before.
        step = phase / 0.9
        i = int(step) % len(VISEMES)
        j = (i + 1) % len(VISEMES)
        t = step - int(step)
    else:
        i = j = target_viseme
        t = 0.0
    eased = t * t * (3 - 2 * t)  # smoothstep -- avoids a linear snap at each viseme boundary
    gate = 0.15 + energy * 0.85  # near-silence still settles mostly closed, never fully rigid
    weights = {
        key: round((VISEMES[i][key] + (VISEMES[j][key] - VISEMES[i][key]) * eased) * gate, 4)
        for key in VISEMES[0]
    }
    weights["eyeBlinkLeft"] = 0.0
    weights["eyeBlinkRight"] = 0.0
    return {"type": "blendshape_frame", "timestamp_ms": timestamp_ms, "weights": weights}


WINDOW_SECONDS = 1.6
STEP_SECONDS = 0.4


def infer_visemes(window: np.ndarray, new_samples: int) -> list[int]:
    """Blocking (real GPU inference) -- always call via asyncio.to_thread.

    Runs the ASR model on the whole window (for acoustic context) but only
    returns visemes for the newest `new_samples` worth of audio -- standard
    sliding-window streaming-ASR technique, so each stretch of audio is only
    ever emitted once even though it's re-scored several times for context.
    """
    import torch

    inputs = _processor(window, sampling_rate=SAMPLE_RATE, return_tensors="pt").input_values.to(_device)
    with torch.no_grad():
        logits = _model(inputs).logits[0]  # [timesteps, vocab]
    ids = torch.argmax(logits, dim=-1).tolist()
    chars = _processor.tokenizer.convert_ids_to_tokens(ids)
    new_fraction = new_samples / len(window)
    new_step_count = max(1, round(len(chars) * new_fraction))
    return [char_to_viseme(ch) for ch in chars[-new_step_count:]]


@dataclass
class ConnectionState:
    pcm_buffer: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    scored_samples: int = 0
    viseme_queue: deque[int] = field(default_factory=deque)
    current_viseme: int | None = None
    inference_busy: bool = False
    energy: float = 0.0


async def _pump_ffmpeg_output(proc: asyncio.subprocess.Process, state: ConnectionState) -> None:
    """Reads decoded PCM from ffmpeg, buffers it, and kicks off inference
    every STEP_SECONDS of new audio -- runs for the life of the connection."""
    assert proc.stdout is not None
    pending = b""
    while True:
        chunk = await proc.stdout.read(4096)
        if not chunk:
            return
        pending += chunk
        usable = len(pending) - (len(pending) % 2)
        if usable <= 0:
            continue
        samples = np.frombuffer(pending[:usable], dtype="<i2").astype(np.float32) / 32768.0
        pending = pending[usable:]
        state.pcm_buffer = np.concatenate([state.pcm_buffer, samples])
        new_samples = len(state.pcm_buffer) - state.scored_samples
        if new_samples < STEP_SECONDS * SAMPLE_RATE or state.inference_busy or _model is None:
            continue
        window = state.pcm_buffer[-int(WINDOW_SECONDS * SAMPLE_RATE) :]
        state.scored_samples = len(state.pcm_buffer)
        state.inference_busy = True
        started = time.perf_counter()
        try:
            visemes = await asyncio.to_thread(infer_visemes, window, new_samples)
            metrics.inference_ms.append((time.perf_counter() - started) * 1000)
            state.viseme_queue.extend(visemes)
            # The emission loop drains this queue at a rate driven by the
            # client's declared (estimated, byte-count-based) audio duration,
            # which won't exactly match how much audio actually reached the
            # model -- so nothing here guarantees drain rate == fill rate.
            # Cap it rather than let a slow-draining client fall further and
            # further behind real time: drop the oldest queued visemes, never
            # let stale ones play back minutes late.
            max_queued = int(2.0 * SAMPLE_RATE / 320)  # ~2s of queued visemes at ~20ms/step
            while len(state.viseme_queue) > max_queued:
                state.viseme_queue.popleft()
            log.info(
                "inference ok: %d new samples -> %d visemes in %.1fms (queue depth %d)",
                new_samples, len(visemes), (time.perf_counter() - started) * 1000, len(state.viseme_queue),
            )
        except Exception:
            log.exception("inference failed -- falling back to heuristic for this stretch")
        finally:
            state.inference_busy = False


async def _receive_loop(
    websocket: WebSocket, state: ConnectionState, proc: asyncio.subprocess.Process | None
) -> None:
    """Reads audio chunks from the client and forwards them to ffmpeg --
    nothing here ever sends a frame back. Emission used to happen right in
    this loop, sized off of *this one received chunk's* byte length -- fine
    for a steady trickle of small chunks, but a real TTS client sends a
    whole utterance as one or two large bursts (confirmed live: a single
    ~37KB message for one reply), and that per-message size estimate was
    capped at 180ms regardless of how much audio actually arrived. The
    result: ~11 frames got sent for the start of the utterance, then the
    socket went silent waiting for another message that never came, while
    the ASR inference queue kept filling in the background and pegged at
    its cap, undrained -- the mouth would twitch for ~180ms then freeze.
    Emission is now driven by _emit_loop's own steady clock instead."""
    while True:
        payload = await websocket.receive()
        if "bytes" in payload and payload["bytes"] is not None:
            chunk = payload["bytes"]
        elif "text" in payload and payload["text"] is not None:
            try:
                decoded = json.loads(payload["text"])
                chunk = bytes(decoded.get("audio", []))
            except Exception:
                chunk = b""
        else:
            chunk = b""
        if proc is not None and proc.stdin is not None and chunk:
            try:
                proc.stdin.write(chunk)
                await proc.stdin.drain()
            except Exception:
                log.exception("ffmpeg pipe broke -- falling back to heuristic for the rest of this connection")
        if chunk:
            state.energy = chunk_energy(chunk)
            metrics.audio_buffer_ms = max(33, min(180, int(len(chunk) / 96)))


async def _emit_loop(websocket: WebSocket, state: ConnectionState) -> None:
    """Sends one blendshape_frame every 16ms for the life of the
    connection, decoupled from when (or how much) audio arrives -- drains
    whatever the ASR pump has queued at a steady, real-time pace instead of
    only when a new client message shows up."""
    phase = 0.0
    timestamp_ms = 0
    while True:
        timestamp_ms += 16
        phase += 0.35 + state.energy * 0.4
        if state.viseme_queue:
            state.current_viseme = state.viseme_queue.popleft()
        frame = make_frame(timestamp_ms, state.energy, phase, state.current_viseme)
        await websocket.send_json(frame)
        metrics.frames += 1
        await asyncio.sleep(0.016)


@app.websocket("/ws/face")
async def face_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    state = ConnectionState()
    proc: asyncio.subprocess.Process | None = None
    pump_task: asyncio.Task | None = None
    if _model is not None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "mp3", "-i", "pipe:0",
                "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "pipe:1",
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            pump_task = asyncio.create_task(_pump_ffmpeg_output(proc, state))
        except Exception:
            log.exception("could not start ffmpeg -- falling back to heuristic for this connection")
            proc = None
    receive_task = asyncio.create_task(_receive_loop(websocket, state, proc))
    emit_task = asyncio.create_task(_emit_loop(websocket, state))
    try:
        done, pending = await asyncio.wait(
            [receive_task, emit_task], return_when=asyncio.FIRST_COMPLETED
        )
        for task in done:
            task.result()
    except WebSocketDisconnect:
        return
    finally:
        receive_task.cancel()
        emit_task.cancel()
        await asyncio.gather(receive_task, emit_task, return_exceptions=True)
        if pump_task is not None:
            pump_task.cancel()
        if proc is not None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
                proc.kill()
            except Exception:
                pass
