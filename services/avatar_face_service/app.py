from __future__ import annotations

import asyncio
import json
import math
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(title="BioTwin Avatar Face Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
        "model_loaded": False,
        "backend": "procedural_audio_fallback",
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
    }


def chunk_energy(chunk: bytes) -> float:
    if not chunk:
        return 0.0
    # MP3 bytes are compressed, so this is not true PCM RMS. It is a fast,
    # deterministic envelope proxy until Audio2Face replaces this backend.
    sample = chunk[: min(len(chunk), 4096)]
    mean = sum(abs(byte - 128) for byte in sample) / len(sample)
    return max(0.0, min(1.0, mean / 82.0))


# A small set of distinct viseme-like mouth shapes to cycle through, instead
# of driving jawOpen/mouthFunnel/mouthPucker/mouthStretch all off one shared
# sine wave -- that made every shape rise and fall together, which reads as
# a single hinge opening and closing, not speech. This still isn't real
# phoneme detection (no audio content is analyzed, just energy + a cycle
# timer), but distinct shapes in sequence read as talking, not a hinge.
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


def make_frame(timestamp_ms: int, energy: float, phase: float) -> dict[str, Any]:
    step = phase / 0.9
    i = int(step) % len(VISEMES)
    j = (i + 1) % len(VISEMES)
    t = step - int(step)
    eased = t * t * (3 - 2 * t)  # smoothstep -- avoids a linear snap at each viseme boundary
    gate = 0.15 + energy * 0.85  # near-silence still settles mostly closed, never fully rigid
    weights = {
        key: round((VISEMES[i][key] + (VISEMES[j][key] - VISEMES[i][key]) * eased) * gate, 4)
        for key in VISEMES[0]
    }
    weights["eyeBlinkLeft"] = 0.0
    weights["eyeBlinkRight"] = 0.0
    return {"type": "blendshape_frame", "timestamp_ms": timestamp_ms, "weights": weights}


@app.websocket("/ws/face")
async def face_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    phase = 0.0
    timestamp_ms = 0
    try:
        while True:
            started = time.perf_counter()
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
            energy = chunk_energy(chunk)
            estimated_ms = max(33, min(180, int(len(chunk) / 96)))
            metrics.audio_buffer_ms = estimated_ms
            frames = max(1, estimated_ms // 16)
            for _ in range(frames):
                timestamp_ms += 16
                phase += 0.35 + energy * 0.4
                frame = make_frame(timestamp_ms, energy, phase)
                await websocket.send_json(frame)
                metrics.frames += 1
                await asyncio.sleep(0)
            metrics.inference_ms.append((time.perf_counter() - started) * 1000)
    except WebSocketDisconnect:
        return

