# BioTwin Avatar Face Service

FastAPI/WebSocket service for the browser avatar's lip sync.

Current backend:

- `asr_viseme:facebook/wav2vec2-base-960h` when the model loads (GPU, real
  speech recognition mapped to mouth shapes by recognized letter -- see
  docs/AVATAR_IMPLEMENTATION_PLAN.md's "Lip sync" section for exactly what
  this is and isn't); falls back to a procedural shape-cycling heuristic
  when the model isn't loaded (no GPU/torch, or a stretch of audio not yet
  scored).
- Streams ARKit-compatible facial blendshape frames from incoming audio chunks.
- Keeps the same API contract intended for a real NVIDIA Audio2Face swap,
  if NGC/NVIDIA registry access ever becomes available.

Endpoints:

- `GET /health`
- `GET /metrics`
- `WS /ws/face`

Deployment path on SCC:

```bash
/data/saurav/avatar_face_service
```

Runtime environment (NOT the directory of the same service name --
that one is Python 3.14, too new for a stable PyTorch wheel):

```bash
/data/saurav/envs/avatar_face_lipsync
```

Start:

```bash
/data/saurav/avatar_face_service/start.sh
```

See also `services/avatar_body_service/` -- a separate, parallel service
for real-time body-gesture generation, same audio in, a different port
and WebSocket.
