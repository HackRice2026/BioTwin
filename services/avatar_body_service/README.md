# BioTwin Avatar Body Service

FastAPI/WebSocket service for the browser avatar's body gestures --
runs in parallel with `avatar_face_service` (same audio, a different port
and endpoint), not instead of it.

Current backend:

- `H-Liu1997/emage_audio` (EMAGE, CVPR 2024) when the model loads (GPU,
  real full-body co-speech gesture generation -- see
  docs/AVATAR_IMPLEMENTATION_PLAN.md's "Body gestures" section for the
  retargeting method, the license caveat, and how this was verified);
  disabled entirely when the model isn't loaded (no fallback heuristic --
  there's no meaningful "guess" for body pose the way there is for a
  mouth-shape cycle, so the avatar just keeps its procedural pose).
- Streams `[x, y, z]` axis-angle rotation deltas (already sign-corrected
  for this rig) per bone, for the bones in `SMPLX_TO_BONE`.

Endpoints:

- `GET /health`
- `GET /metrics`
- `WS /ws/body`

Deployment path on SCC:

```bash
/data/saurav/avatar_body_service
```

Runtime environment (also needs the EMAGE repo itself on `PYTHONPATH`,
see `start.sh`):

```bash
/data/saurav/envs/emage
/data/saurav/emage          # git clone of PantoMatrix/PantoMatrix
```

Start:

```bash
/data/saurav/avatar_body_service/start.sh
```
