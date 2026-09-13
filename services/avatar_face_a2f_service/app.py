from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("avatar_face_a2f_service")

app = FastAPI(title="BioTwin Avatar Face Service (Audio2Face-3D)")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_RATE = 16000
FRAME_RATE = 60.0  # matches the "60, 1" frame-rate params passed into the bridge's bundle
FRAME_INTERVAL = 1.0 / FRAME_RATE

# Real NVIDIA Audio2Face-3D SDK bridge (services/audio2face_sdk_bridge/), built
# against the SDK checkout on this box -- see that directory's README and
# docs/AVATAR_IMPLEMENTATION_PLAN.md for how it got here and why it is
# single-utterance-per-process (short version: reusing one bundle across
# utterances in the same process reproducibly corrupted the second utterance's
# output -- see that doc for the full investigation. One process per
# utterance is the only configuration that has ever come back clean).
BRIDGE_BINARY = os.environ.get(
    "A2F_BRIDGE_BINARY",
    "/data/saurav/audio2face-sdk/_build/release/audio2face-sdk/bin/sample-a2f-blendshape-print",
)
MODEL_JSON_PATH = os.environ.get(
    "A2F_MODEL_JSON",
    "/data/saurav/audio2face-sdk/_data/generated/audio2face-sdk/samples/data/mark/model.json",
)
POOL_SIZE = int(os.environ.get("A2F_POOL_SIZE", "2"))
READY_TIMEOUT_S = 15.0

# How long a connection waits with no new decoded audio before treating
# whatever is buffered as one complete utterance and sending it off for
# inference. TTS audio arrives in a handful of large bursts per utterance,
# not a steady trickle, so a real gap is a reliable utterance boundary.
SILENCE_FLUSH_S = 0.5
SILENCE_POLL_S = 0.05


class BridgeProcess:
    """One live subprocess running the Audio2Face-3D bridge, good for
    exactly one utterance before it exits on its own."""

    def __init__(self, proc: asyncio.subprocess.Process) -> None:
        self.proc = proc

    async def run_utterance(self, pcm_f32_bytes: bytes) -> list[dict[str, Any]]:
        assert self.proc.stdin is not None
        assert self.proc.stdout is not None
        self.proc.stdin.write(struct.pack("<I", len(pcm_f32_bytes)))
        self.proc.stdin.write(pcm_f32_bytes)
        await self.proc.stdin.drain()
        self.proc.stdin.close()

        frames: list[dict[str, Any]] = []
        while True:
            line = await self.proc.stdout.readline()
            if not line:
                break
            try:
                parsed = json.loads(line)
            except ValueError:
                continue
            if parsed.get("utterance_done"):
                break
            frames.append(parsed)
        return frames


async def _spawn_bridge_process() -> BridgeProcess:
    proc = await asyncio.create_subprocess_exec(
        BRIDGE_BINARY, MODEL_JSON_PATH,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    assert proc.stderr is not None
    try:
        line = await asyncio.wait_for(proc.stderr.readline(), timeout=READY_TIMEOUT_S)
    except asyncio.TimeoutError:
        proc.kill()
        raise RuntimeError("bridge process did not report ready in time")
    if b"ready" not in line:
        proc.kill()
        raise RuntimeError(f"bridge process did not report ready, got: {line!r}")
    return BridgeProcess(proc)


class BridgePool:
    """Keeps POOL_SIZE bridge processes warm (model already loaded) at all
    times. Each checked-out process is used for exactly one utterance and
    then discarded -- reusing one across utterances is what produced
    corrupted (NaN) output in testing (see docs/AVATAR_IMPLEMENTATION_PLAN.md).
    A replacement is spawned in the background as soon as one is checked
    out, so the pool refills without blocking whichever request needed it."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._queue: asyncio.Queue[BridgeProcess] = asyncio.Queue()
        self._spawn_failures = 0

    async def start(self) -> None:
        for _ in range(self.size):
            asyncio.create_task(self._replenish_one())

    async def _replenish_one(self) -> None:
        try:
            bridge = await _spawn_bridge_process()
        except Exception:
            self._spawn_failures += 1
            log.exception("failed to spawn a warm bridge process")
            return
        await self._queue.put(bridge)

    async def checkout(self) -> BridgeProcess:
        bridge = await self._queue.get()
        asyncio.create_task(self._replenish_one())
        return bridge

    def qsize(self) -> int:
        return self._queue.qsize()


pool = BridgePool(POOL_SIZE)


@app.on_event("startup")
async def _startup() -> None:
    await pool.start()


@dataclass
class Metrics:
    utterances: int = 0
    frames_emitted: int = 0
    inference_ms: deque[float] = field(default_factory=lambda: deque(maxlen=60))
    started_at: float = field(default_factory=time.perf_counter)

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
        "backend": "audio2face_3d_sdk",
        "warm_pool_size": pool.qsize(),
        "pool_target": pool.size,
        "spawn_failures": pool._spawn_failures,
    }


@app.get("/metrics")
def get_metrics() -> dict[str, Any]:
    gpu = gpu_snapshot()
    return {
        "utterances": metrics.utterances,
        "frames_emitted": metrics.frames_emitted,
        "avg_inference_ms": round(metrics.avg_inference_ms, 1),
        "warm_pool_size": pool.qsize(),
        "gpu_utilization": gpu["gpu_utilization"],
        "vram_mb": gpu["vram_mb"],
    }


@dataclass
class ConnectionState:
    pcm_chunks: list[bytes] = field(default_factory=list)
    last_audio_at: float = 0.0
    frame_queue: deque[dict[str, Any]] = field(default_factory=deque)


async def _pump_ffmpeg_output(proc: asyncio.subprocess.Process, state: ConnectionState) -> None:
    """Reads decoded 16kHz mono s16le PCM from ffmpeg and buffers it as raw
    float32 bytes (the bridge's wire format), for the life of the connection."""
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
        import numpy as np

        samples = np.frombuffer(pending[:usable], dtype="<i2").astype("float32") / 32768.0
        pending = pending[usable:]
        state.pcm_chunks.append(samples.tobytes())
        state.last_audio_at = time.monotonic()


async def _utterance_flush_loop(state: ConnectionState) -> None:
    """Watches for a gap in incoming audio and, once seen, hands whatever
    is buffered off to a warm bridge process for inference. Runs for the
    life of the connection."""
    while True:
        await asyncio.sleep(SILENCE_POLL_S)
        if not state.pcm_chunks:
            continue
        if time.monotonic() - state.last_audio_at < SILENCE_FLUSH_S:
            continue
        pcm_bytes = b"".join(state.pcm_chunks)
        state.pcm_chunks.clear()
        asyncio.create_task(_run_utterance(pcm_bytes, state))


async def _run_utterance(pcm_bytes: bytes, state: ConnectionState) -> None:
    try:
        bridge = await pool.checkout()
    except Exception:
        log.exception("could not check out a bridge process -- dropping this utterance")
        return
    started = time.perf_counter()
    try:
        frames = await bridge.run_utterance(pcm_bytes)
    except Exception:
        log.exception("bridge inference failed -- dropping this utterance")
        return
    finally:
        try:
            await asyncio.wait_for(bridge.proc.wait(), timeout=5.0)
        except Exception:
            bridge.proc.kill()
    metrics.inference_ms.append((time.perf_counter() - started) * 1000)
    metrics.utterances += 1
    for frame in frames:
        state.frame_queue.append(frame)
    log.info(
        "utterance done: %d samples -> %d frames in %.1fms",
        len(pcm_bytes) // 4, len(frames), (time.perf_counter() - started) * 1000,
    )


@app.websocket("/ws/face")
async def face_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    state = ConnectionState(last_audio_at=time.monotonic())
    timestamp_ms = 0

    proc = await asyncio.create_subprocess_exec(
        "ffmpeg", "-hide_banner", "-loglevel", "error",
        "-f", "mp3", "-i", "pipe:0",
        "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "pipe:1",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    pump_task = asyncio.create_task(_pump_ffmpeg_output(proc, state))
    flush_task = asyncio.create_task(_utterance_flush_loop(state))

    async def emit_loop() -> None:
        nonlocal timestamp_ms
        while True:
            await asyncio.sleep(FRAME_INTERVAL)
            if not state.frame_queue:
                continue
            # Emission is decoupled from inference arrival on purpose: a
            # whole utterance's frames come back at once (batch inference,
            # not streamed per-frame), so drain this queue at the network's
            # own frame rate rather than dumping them all in one message.
            raw = state.frame_queue.popleft()
            timestamp_ms += int(FRAME_INTERVAL * 1000)
            await websocket.send_json({
                "type": "blendshape_frame",
                "timestamp_ms": timestamp_ms,
                "weights": raw.get("weights", {}),
            })
            metrics.frames_emitted += 1

    emit_task = asyncio.create_task(emit_loop())

    try:
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
            if chunk and proc.stdin is not None:
                try:
                    proc.stdin.write(chunk)
                    await proc.stdin.drain()
                except Exception:
                    log.exception("ffmpeg pipe broke for this connection")
    except WebSocketDisconnect:
        return
    finally:
        for task in (pump_task, flush_task, emit_task):
            task.cancel()
        try:
            if proc.stdin is not None:
                proc.stdin.close()
            proc.kill()
        except Exception:
            pass
