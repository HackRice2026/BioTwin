"""Manual end-to-end check for the real ASR-driven lip sync path.

Not part of the `uv run pytest` suite -- it needs a running instance of this
service with the real model loaded (GPU + torch + transformers + ffmpeg),
which only exists on the SCC box today, not in CI. Run it there:

    uv run --python /data/saurav/envs/avatar_face_lipsync/bin/python \\
        services/avatar_face_service/test_lipsync.py [ws://host:port/ws/face] [audio.mp3]

Streams a real MP3 (any speech clip; an ElevenLabs export works fine) to the
service exactly as the browser does -- raw compressed bytes, chunked -- and
prints the received blendshape frames as a collapsed dominant-shape timeline,
so you can see whether the mouth shape sequence tracks the audio content
instead of a fixed cycle. This does not by itself prove the MODEL path ran
(the no-model heuristic fallback also produces varied shapes) -- for that,
check the service's own stdout/log for "inference ok: N new samples -> M
visemes in T ms" lines, which only print when a real inference call
completed.
"""

import asyncio
import json
import sys

import websockets

DEFAULT_URL = "ws://127.0.0.1:8765/ws/face"


async def main() -> None:
    url = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_URL
    audio_path = sys.argv[2] if len(sys.argv) > 2 else None
    if not audio_path:
        raise SystemExit("Usage: test_lipsync.py [ws_url] <path/to/speech.mp3>")

    with open(audio_path, "rb") as f:
        data = f.read()
    chunk_size = 4096
    chunks = [data[i : i + chunk_size] for i in range(0, len(data), chunk_size)]

    frames: list[dict] = []
    async with websockets.connect(url, max_size=None) as ws:
        async def sender():
            for c in chunks:
                await ws.send(c)
                await asyncio.sleep(0.05)

        async def receiver():
            try:
                async with asyncio.timeout(10):
                    while True:
                        frames.append(json.loads(await ws.recv()))
            except (TimeoutError, websockets.exceptions.ConnectionClosed):
                pass

        await asyncio.gather(sender(), receiver())

    print(f"sent {len(chunks)} chunks ({len(data)} bytes), received {len(frames)} frames")
    labels = [max(f["weights"].items(), key=lambda kv: kv[1])[0][:10] for f in frames]
    collapsed: list[str] = []
    for label in labels:
        if not collapsed or collapsed[-1] != label:
            collapsed.append(label)
    print("dominant-shape timeline:", " -> ".join(collapsed))


if __name__ == "__main__":
    asyncio.run(main())
