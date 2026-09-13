from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("avatar_body_service")

app = FastAPI(title="BioTwin Avatar Body Service")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

SAMPLE_RATE = 16000
MODEL_SOURCE = "H-Liu1997/emage_audio"

# SMPL-X joint (axis-angle, radians) -> this rig's bone name. Covers
# spine/neck/head/arms/legs plus fingers. Not mapped: EMAGE's jaw and
# left/right_eye_smplhf joints -- the jaw would fight the ASR lip-sync
# service's own jawOpen morph target, and eyes would fight the existing
# gaze system, so both are deliberately left alone here rather than
# having two systems drive the same feature.
#
# SMPL-X gives 3 joints per finger (e.g. left_index1/2/3); this rig has 4
# segments per finger (LeftHandIndex1-4). Mapped 1:1 through segment 3;
# segment 4 (a short distal/tip bone) is left at rest -- there's no 4th
# SMPL-X joint to drive it from, and leaving it untouched is a safe
# default rather than guessing.
SMPLX_TO_BONE: dict[str, str] = {
    "spine1": "Spine",
    "spine2": "Spine1",
    "spine3": "Spine2",
    "neck": "Neck",
    "head": "Head",
    "left_collar": "LeftShoulder",
    "right_collar": "RightShoulder",
    "left_shoulder": "LeftArm",
    "right_shoulder": "RightArm",
    "left_elbow": "LeftForeArm",
    "right_elbow": "RightForeArm",
    "left_wrist": "LeftHand",
    "right_wrist": "RightHand",
    "left_hip": "LeftUpLeg",
    "right_hip": "RightUpLeg",
    "left_knee": "LeftLeg",
    "right_knee": "RightLeg",
    "left_ankle": "LeftFoot",
    "right_ankle": "RightFoot",
    **{
        f"{side}_{finger}{n}": f"{Side}Hand{Finger}{n}"
        for side, Side in (("left", "Left"), ("right", "Right"))
        for finger, Finger in (
            ("thumb", "Thumb"),
            ("index", "Index"),
            ("middle", "Middle"),
            ("ring", "Ring"),
            ("pinky", "Pinky"),
        )
        for n in (1, 2, 3)
    },
}

_model = None
_motion_vq = None
_joint_index: dict[str, int] = {}
_device = "cpu"


def load_model() -> None:
    global _model, _motion_vq, _joint_index, _device
    try:
        import torch
        from smplx import joint_names
        from models.emage_audio import EmageAudioModel, EmageVAEConv, EmageVQModel, EmageVQVAEConv
    except ImportError:
        log.warning("torch/transformers/smplx not installed -- body gestures will stay disabled")
        return
    _device = "cuda" if torch.cuda.is_available() else "cpu"
    try:
        face_vq = EmageVQVAEConv.from_pretrained(MODEL_SOURCE, subfolder="emage_vq/face").to(_device)
        upper_vq = EmageVQVAEConv.from_pretrained(MODEL_SOURCE, subfolder="emage_vq/upper").to(_device)
        lower_vq = EmageVQVAEConv.from_pretrained(MODEL_SOURCE, subfolder="emage_vq/lower").to(_device)
        hands_vq = EmageVQVAEConv.from_pretrained(MODEL_SOURCE, subfolder="emage_vq/hands").to(_device)
        global_ae = EmageVAEConv.from_pretrained(MODEL_SOURCE, subfolder="emage_vq/global").to(_device)
        motion_vq = EmageVQModel(
            face_model=face_vq, upper_model=upper_vq, lower_model=lower_vq,
            hands_model=hands_vq, global_model=global_ae,
        ).to(_device)
        motion_vq.eval()
        model = EmageAudioModel.from_pretrained(MODEL_SOURCE).to(_device)
        model.eval()
        _model = model
        _motion_vq = motion_vq
        _joint_index = {name: i for i, name in enumerate(joint_names.JOINT_NAMES[:55])}
        log.info("loaded %s on %s", MODEL_SOURCE, _device)
    except Exception:
        log.exception("failed to load %s -- body gestures will stay disabled", MODEL_SOURCE)
        _model = None
        _motion_vq = None


@app.on_event("startup")
def _startup() -> None:
    load_model()


@dataclass
class Metrics:
    frames: int = 0
    inference_ms: deque[float] = field(default_factory=lambda: deque(maxlen=180))
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
            ["nvidia-smi", "--query-gpu=name,utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
            text=True, timeout=2,
        )
    except Exception:
        return {"gpu": "unavailable", "gpu_utilization": 0, "vram_mb": 0}
    first = output.strip().splitlines()[0].split(",")
    if len(first) < 3:
        return {"gpu": output.strip() or "unknown", "gpu_utilization": 0, "vram_mb": 0}
    return {"gpu": first[0].strip(), "gpu_utilization": int(first[1].strip() or 0), "vram_mb": int(first[2].strip() or 0)}


@app.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", **gpu_snapshot(), "model_loaded": _model is not None, "backend": MODEL_SOURCE if _model else "disabled"}


@app.get("/metrics")
def get_metrics() -> dict[str, Any]:
    gpu = gpu_snapshot()
    return {
        "frames": metrics.frames,
        "avg_inference_ms": round(metrics.avg_inference_ms, 3),
        "gpu_utilization": gpu["gpu_utilization"],
        "vram_mb": gpu["vram_mb"],
        "model_loaded": _model is not None,
    }


WINDOW_SECONDS = 5.0
STEP_SECONDS = 1.0
POSE_FPS = 30


def infer_bone_deltas(window: "np.ndarray", new_samples: int) -> list[dict[str, list[float]]]:
    """Blocking (real GPU inference) -- always call via asyncio.to_thread.

    Runs EMAGE on the whole window (context) but only returns bone-rotation
    deltas for the newest `new_samples` worth of audio, same sliding-window
    technique as the face service's ASR model. Each returned dict maps this
    rig's bone name to a [x, y, z] axis-angle vector, already negated to
    match this rig's rotation convention (see docs/AVATAR_IMPLEMENTATION_PLAN.md
    "Body gestures" section for how that sign was determined) -- the client
    builds the quaternion and composes it onto the bone's own rest pose.
    """
    import torch
    import torch.nn.functional as F

    audio_t = torch.from_numpy(window).to(_device).unsqueeze(0)
    speaker_id = torch.zeros(1, 1, device=_device).long()
    trans = torch.zeros(1, 1, 3, device=_device)
    with torch.no_grad():
        latent_dict = _model.inference(audio_t, speaker_id, _motion_vq, masked_motion=None, mask=None)
        cfg = _model.cfg
        face_latent = latent_dict["rec_face"] if cfg.lf > 0 and cfg.cf == 0 else None
        upper_latent = latent_dict["rec_upper"] if cfg.lu > 0 and cfg.cu == 0 else None
        hands_latent = latent_dict["rec_hands"] if cfg.lh > 0 and cfg.ch == 0 else None
        lower_latent = latent_dict["rec_lower"] if cfg.ll > 0 and cfg.cl == 0 else None
        face_index = torch.max(F.log_softmax(latent_dict["cls_face"], dim=2), dim=2)[1] if cfg.cf > 0 else None
        upper_index = torch.max(F.log_softmax(latent_dict["cls_upper"], dim=2), dim=2)[1] if cfg.cu > 0 else None
        hands_index = torch.max(F.log_softmax(latent_dict["cls_hands"], dim=2), dim=2)[1] if cfg.ch > 0 else None
        lower_index = torch.max(F.log_softmax(latent_dict["cls_lower"], dim=2), dim=2)[1] if cfg.cl > 0 else None
        all_pred = _motion_vq.decode(
            face_latent=face_latent, upper_latent=upper_latent, lower_latent=lower_latent, hands_latent=hands_latent,
            face_index=face_index, upper_index=upper_index, lower_index=lower_index, hands_index=hands_index,
            get_global_motion=True, ref_trans=trans[:, 0],
        )
    motion = all_pred["motion_axis_angle"].cpu().numpy().reshape(-1, 55, 3)  # [T, 55, 3]
    new_frame_count = max(1, round(new_samples / SAMPLE_RATE * POSE_FPS))
    newest = motion[-new_frame_count:]
    frames: list[dict[str, list[float]]] = []
    for t in range(newest.shape[0]):
        bones: dict[str, list[float]] = {}
        for smplx_name, bone_name in SMPLX_TO_BONE.items():
            aa = newest[t, _joint_index[smplx_name]]
            bones[bone_name] = [-float(aa[0]), -float(aa[1]), -float(aa[2])]
        frames.append(bones)
    return frames


@dataclass
class ConnectionState:
    pcm_buffer: "np.ndarray" = field(default_factory=lambda: np.zeros(0, dtype=np.float32))
    scored_samples: int = 0
    frame_queue: deque = field(default_factory=deque)
    inference_busy: bool = False


async def _pump_ffmpeg_output(proc: "asyncio.subprocess.Process", state: ConnectionState) -> None:
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
        window = state.pcm_buffer[-int(WINDOW_SECONDS * SAMPLE_RATE):]
        state.scored_samples = len(state.pcm_buffer)
        state.inference_busy = True
        started = time.perf_counter()
        try:
            frames = await asyncio.to_thread(infer_bone_deltas, window, new_samples)
            elapsed_ms = (time.perf_counter() - started) * 1000
            metrics.inference_ms.append(elapsed_ms)
            state.frame_queue.extend(frames)
            max_queued = int(2.0 * POSE_FPS)  # ~2s of queued frames, oldest dropped first
            while len(state.frame_queue) > max_queued:
                state.frame_queue.popleft()
            log.info(
                "inference ok: %d new samples -> %d body frames in %.1fms (queue depth %d)",
                new_samples, len(frames), elapsed_ms, len(state.frame_queue),
            )
        except Exception:
            log.exception("body inference failed for this stretch")
        finally:
            state.inference_busy = False


async def _receive_loop(websocket: WebSocket, proc: "asyncio.subprocess.Process | None") -> None:
    """Only responsible for pulling audio off the socket and feeding ffmpeg.
    Emission used to happen inline here too, gated by how many chunks the
    client happened to send -- real audio arrives in a handful of large
    bursts (not evenly paced small chunks), so frames piled up in the queue
    and were never actually sent. Emission is now a fully separate,
    independently-timed task (_emit_loop) so it isn't coupled to input
    arrival at all."""
    while True:
        payload = await websocket.receive()
        chunk = b""
        if "bytes" in payload and payload["bytes"] is not None:
            chunk = payload["bytes"]
        elif "text" in payload and payload["text"] is not None:
            try:
                chunk = bytes(json.loads(payload["text"]).get("audio", []))
            except Exception:
                chunk = b""
        if proc is not None and proc.stdin is not None and chunk:
            try:
                proc.stdin.write(chunk)
                await proc.stdin.drain()
            except Exception:
                log.exception("ffmpeg pipe broke -- body gestures disabled for the rest of this connection")


async def _emit_loop(websocket: WebSocket, state: "ConnectionState") -> None:
    timestamp_ms = 0
    frame_interval = 1 / POSE_FPS
    while True:
        await asyncio.sleep(frame_interval)
        timestamp_ms += int(frame_interval * 1000)
        if not state.frame_queue:
            continue  # nothing queued -- client keeps its last pose, no heuristic fallback for body gestures
        bones = state.frame_queue.popleft()
        await websocket.send_json({"type": "body_frame", "timestamp_ms": timestamp_ms, "bones": bones})
        metrics.frames += 1


@app.websocket("/ws/body")
async def body_socket(websocket: WebSocket) -> None:
    await websocket.accept()
    state = ConnectionState()
    proc: "asyncio.subprocess.Process | None" = None
    if _model is not None:
        try:
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "mp3", "-i", "pipe:0",
                "-f", "s16le", "-ar", str(SAMPLE_RATE), "-ac", "1", "pipe:1",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )
        except Exception:
            log.exception("could not start ffmpeg -- body gestures disabled for this connection")
            proc = None
    tasks = [asyncio.create_task(_receive_loop(websocket, proc))]
    if proc is not None:
        tasks.append(asyncio.create_task(_pump_ffmpeg_output(proc, state)))
        tasks.append(asyncio.create_task(_emit_loop(websocket, state)))
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            exc = task.exception()
            if exc is not None and not isinstance(exc, WebSocketDisconnect):
                log.exception("body service task ended unexpectedly", exc_info=exc)
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        if proc is not None:
            try:
                if proc.stdin is not None:
                    proc.stdin.close()
                proc.kill()
            except Exception:
                pass
