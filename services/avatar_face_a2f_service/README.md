# Avatar Face Service (Audio2Face-3D)

Real NVIDIA Audio2Face-3D SDK lip sync, as an alternative backend to
`services/avatar_face_service`'s ASR-based viseme heuristic. Same
`/ws/face` protocol and `blendshape_frame` message shape, so the frontend
does not need to change to switch between them -- just which port it
connects to.

Not merged into `dev` yet -- this lives on the `mesh` branch. See
`docs/AVATAR_IMPLEMENTATION_PLAN.md` for the full story of how the
Audio2Face-3D SDK bridge (`services/audio2face_sdk_bridge/`) was built,
verified, and why it's used the way it is here.

## Why a process pool instead of one long-lived inference process

The bridge is single-utterance-per-process by design: reusing one
Audio2Face-3D bundle across multiple utterances in the same process --
tried three different ways (resetting the executor/accumulators between
utterances, never resetting and just accumulating one continuous stream,
and discarding the whole bundle for a genuinely fresh one per utterance)
-- reproducibly corrupted the second utterance's output (all blendshape
weights NaN from frame 0), even in the fully-fresh-bundle case where
nothing from the first utterance's objects was touched again. That
points to some process-global GPU/allocator state this SDK doesn't
expose a way to reset. Full investigation in the plan doc.

So instead: `BridgePool` keeps a small number of bridge processes warm
(model already loaded, sitting at "ready") at all times. When an
utterance needs processing, one is checked out, fed that utterance's
audio, and discarded once it finishes (the process exits on its own
after one utterance) -- a replacement is spawned in the background
immediately, so the ~1-3s model-load cost is paid ahead of time rather
than adding latency to the utterance that needed a process.

## Utterance boundaries

There is no explicit "utterance start/end" message in the existing
`/ws/face` protocol -- audio just streams in as MP3 chunks for the life
of the connection. This service treats a gap of `SILENCE_FLUSH_S`
(currently 0.5s) with no new decoded audio as the end of one utterance:
whatever PCM has buffered up to that point is handed to a warm bridge
process, and buffering starts over for the next one. This matches how
TTS audio actually arrives in practice (a handful of large bursts per
utterance, then quiet) rather than a steady trickle.

## Running

Same shape as `avatar_face_service` and `avatar_body_service`: a
`start.sh` that activates the shared `avatar_face_lipsync` venv (this
service only needs fastapi/uvicorn/numpy, already in that venv) and
runs `uvicorn app:app` on port 8767 by default. Point `A2F_BRIDGE_BINARY`
and `A2F_MODEL_JSON` at a different build/model if the SDK checkout
moves; both currently default to this box's paths under
`/data/saurav/audio2face-sdk/`.
