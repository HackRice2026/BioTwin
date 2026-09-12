# BioTwin Avatar Face Service

FastAPI/WebSocket service for the browser avatar.

Current backend:

- `procedural_audio_fallback`
- Streams ARKit-compatible facial blendshape frames from incoming audio chunks.
- Keeps the same API contract intended for NVIDIA Audio2Face replacement.

Endpoints:

- `GET /health`
- `GET /metrics`
- `WS /ws/face`

Deployment path on SCC:

```bash
/data/saurav/avatar_face_service
```

Runtime environment:

```bash
/data/saurav/envs/avatar_face_service
```

Start:

```bash
/data/saurav/avatar_face_service/start.sh
```
