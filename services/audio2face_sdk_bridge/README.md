# Audio2Face-3D SDK bridge (in progress)

This directory tracks the source for our own additions to a plain
`git clone` of [`NVIDIA/Audio2Face-3D-SDK`](https://github.com/NVIDIA/Audio2Face-3D-SDK)
(MIT) -- the SDK itself is not vendored into this repo (it's large, and
building it needs a real GPU/CUDA/TensorRT toolchain); it lives at
`/data/saurav/audio2face-sdk` on the SCC box. See
`docs/AVATAR_IMPLEMENTATION_PLAN.md`'s "Real NVIDIA Audio2Face-3D"
section for the full story: how the SDK was built, why an earlier
conclusion here (that ARKit output wasn't achievable) was wrong, and
what's still needed.

## What's here

`sample-a2f-blendshape-print/` -- a small sample we wrote (not part of
NVIDIA's own SDK), proving the SDK's blendshape-solve path produces
real, named, ARKit-compatible blendshape weights on real audio. Deploy
it into the SDK checkout at
`audio2face-sdk/source/samples/sample-a2f-blendshape-print/`, add
`add_subdirectory(sample-a2f-blendshape-print)` to
`audio2face-sdk/source/samples/CMakeLists.txt`, then
`./build.sh all release` from the SDK root (same `TENSORRT_ROOT_DIR`/
`CUDA_PATH` env vars as any other build -- see the plan doc).

## What's not here yet

The actual streaming bridge: a persistent version of this same
blendshape-solve call, reading audio from stdin and writing
newline-delimited JSON blendshape frames to stdout, so a Python service
can run it as a subprocess (the same shape as how
`services/avatar_face_service` already shells out to `ffmpeg`). Once
that exists, it would be a real alternative to the ASR-based lip sync
currently in production -- same content (named ARKit weights), a
different, more purpose-built model behind it.
