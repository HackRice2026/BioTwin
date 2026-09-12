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


def make_frame(timestamp_ms: int, energy: float, phase: float) -> dict[str, Any]:
    vowel = abs(math.sin(phase * 1.7))
    narrow = abs(math.sin(phase * 0.73 + 0.4))
    smile = 0.07 + energy * 0.05
    jaw = min(1.0, 0.04 + energy * 0.72 + vowel * 0.18)
    return {
        "type": "blendshape_frame",
        "timestamp_ms": timestamp_ms,
        "weights": {
            "jawOpen": jaw,
            "mouthClose": max(0.0, 0.2 - jaw * 0.16),
            "mouthFunnel": min(1.0, energy * 0.22 + narrow * 0.12),
            "mouthPucker": min(1.0, narrow * 0.14),
            "mouthSmileLeft": smile,
            "mouthSmileRight": smile,
            "mouthStretchLeft": min(1.0, energy * 0.1 + vowel * 0.07),
            "mouthStretchRight": min(1.0, energy * 0.1 + vowel * 0.07),
            "eyeBlinkLeft": 0.0,
            "eyeBlinkRight": 0.0,
        },
    }


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

