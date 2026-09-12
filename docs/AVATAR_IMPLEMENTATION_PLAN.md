# CURRENT HANDOFF — 3d-gesturing branch

Date: 2026-09-12

Branch: `3d-gesturing`

## Done in this branch

- Switched the browser avatar from the older generated `twin.glb` to the new ARKit-capable avatar at `frontend/public/assets/model.glb`.
- Inspected `docs/model.glb`: it has a humanoid skin, 73 joints, and ARKit-style morph targets including `jawOpen`, `mouthFunnel`, `mouthPucker`, `eyeBlinkLeft`, `eyeBlinkRight`, brows, smiles, frowns, and stretches.
- Added browser avatar runtime files under `frontend/src/avatar/`:
  - semantic avatar state
  - emotion interpolation
  - Audio2Face-style morph mapping
  - audio/semantic event bus
- Rebuilt `frontend/src/Avatar.tsx` around the new model:
  - breathing
  - random blinking
  - gaze/head motion
  - procedural body gestures
  - point, walk, run, nod, celebrate
  - squat demo mode
  - workout HUD
  - smooth camera modes
  - Shift+D debug panel
  - hotkeys `1` through `8`, with `7` for squat demo
- Wired ElevenLabs streaming chunks in `frontend/src/voice.ts` into the avatar audio bus.
- Added deterministic conversation triggers in `frontend/src/useTwinConversation.ts`:
  - exhausted/tired/four-hours style text shifts the coach into concerned/low-energy empathy
  - “show me the squat” triggers squat demo state
- Added a standalone SCC face service under `services/avatar_face_service/`.
- Deployed that service on SCC as user `saurav` only:
  - service path: `/data/saurav/avatar_face_service`
  - venv path: `/data/saurav/envs/avatar_face_service`
  - tmux session: `avatar-face`
- Verified SCC command discipline:
  - all remote commands used `sudo -iu saurav`
  - project service/data stayed under `/data/saurav`
- Verified locally:
  - `npm run build --prefix frontend`
  - `python -m py_compile services/avatar_face_service/app.py`
  - `GET http://127.0.0.1:8765/health`
  - `GET http://127.0.0.1:8765/metrics`
  - `WS /ws/face` returns blendshape frames
  - full app at `http://127.0.0.1:8000` shows `GPU FACE SERVICE: ONLINE`
  - hotkey `7` renders squat movement and HUD

## Important limitation

The SCC service is currently an API-compatible `procedural_audio_fallback`, not NVIDIA Audio2Face yet. It streams ARKit-style blendshape frames from the incoming audio chunk envelope so the app has working mouth/facial motion and the correct WebSocket contract. The next model/agent should replace the internals of `services/avatar_face_service/app.py` with real NVIDIA Audio2Face/TensorRT inference while keeping the same API:

- `GET /health`
- `GET /metrics`
- `WS /ws/face`

## How to run what exists now

On SCC, service should already be running:

```bash
ssh scc
sudo -iu saurav
tmux ls
tmux attach -t avatar-face
```

From the Mac, keep an SSH tunnel open:

```bash
ssh -L 8765:127.0.0.1:8765 scc 'sudo -iu saurav bash -lc "sleep 3600"'
```

Verify:

```bash
curl http://127.0.0.1:8765/health
```

Run the BioTwin app:

```bash
.venv/bin/uvicorn core.api:app --host 127.0.0.1 --port 8000 --no-access-log
```

Open:

```text
http://127.0.0.1:8000
```

Use:

- `Shift+D` for avatar debug panel
- `7` for squat demo
- Ask “I’m exhausted today. I slept four hours.”
- Ask “Show me the squat.”

## Next steps

1. Install and validate real NVIDIA Audio2Face-3D or the correct NVIDIA ACE/Audio2Face runtime under `/data/saurav`, never outside `/data/saurav`.
2. Keep the existing FastAPI/WebSocket contract and replace only the procedural blendshape generator.
3. Benchmark real latency:
   - audio chunk duration
   - inference time
   - face FPS
   - end-to-end face delay
   - GPU utilization
   - VRAM usage
4. Make Gemini return structured avatar state JSON instead of only text:
   - `speech`
   - `emotion`
   - `action`
   - `gaze`
   - `workoutAdjustment`
5. Validate malformed Gemini fallback so the avatar never crashes.
6. Improve exercise choreography after real face backend is stable:
   - better squat timing
   - step-back transition
   - point-to-plan gesture
   - return-to-conversation transition
7. Add real retargeted skeletal animation clips if available; current body motions are procedural bone poses.
8. Add automated browser smoke that checks:
   - model loads
   - morph targets discovered
   - face service online/fallback state
   - hotkey `7` squat HUD
   - no console page errors

---

# OBJECTIVE

Implement the complete real-time 3D fitness avatar experience NOW.

Do not redesign unrelated parts of the app.

Do not replace existing working Gemini or ElevenLabs integration.

We already have:

- Gemini producing conversational text responses
- ElevenLabs producing TTS
- a rigged 3D GLB avatar in the app
- an NVIDIA LaunchPad GPU machine
- persistent user storage under `/data`
- existing Python virtual environments under the `saurav` user
- SSH access to the GPU environment

The goal is to turn the current avatar into a highly polished, emotionally responsive, low-latency, conversational fitness coach with:

- flawless lip sync
- near-instant conversational response
- emotional facial behavior
- natural gaze
- blinking
- breathing
- posture
- gestures
- walking
- running
- exercise demonstrations
- expressive transitions
- workout adaptation
- cinematic presentation

Do not train a custom avatar model unless absolutely required.

Use pretrained real-time inference wherever possible.

---

# CORE SYSTEM ARCHITECTURE

Current text/voice pipeline:

```text
USER VOICE
   ↓
speech input
   ↓
Gemini
   ↓
text response
   ↓
ElevenLabs TTS
   ↓
streaming speech audio
```

Extend it to:

```text
USER VOICE
   ↓
Gemini
   ↓
structured response
   ├───────────────┐
   ↓               ↓
speech text        avatar semantic state
   ↓               ↓
ElevenLabs TTS     emotion/action/gaze/workout state
   ↓
streaming audio
   ├──────────────→ browser audio playback
   ↓
NVIDIA Audio2Face service
   ↓
facial blendshape frames
   ↓
WebSocket
   ↓
browser Three.js avatar
```

The avatar engine should combine:

```text
lip sync
+
emotion
+
blink
+
gaze
+
body animation
+
breathing
+
gesture
+
workout choreography
```

in real time.

---

# CRITICAL LATENCY REQUIREMENT

The experience must feel conversational.

Do NOT wait for full TTS generation before starting playback or facial animation.

Use streaming.

Target:

```text
Gemini response begins
↓
ElevenLabs begins streaming audio
↓
audio begins playing
↓
Audio2Face receives same stream
↓
blendshape frames begin
↓
avatar speaks immediately
```

Do not build a batch workflow like:

```text
generate whole MP3
↓
save
↓
send to face model
↓
wait
↓
play
```

That is unacceptable.

Use persistent connections and incremental streaming.

---

# NVIDIA GPU ENVIRONMENT

The NVIDIA GPU is in NVIDIA LaunchPad.

Access flow:

```bash
ssh scc
```

Then:

```bash
sudo -iu saurav
```

All project storage and persistent files should live under:

```bash
/data
```

Do not install important project assets into ephemeral home/tmp paths if avoidable.

Before changing anything:

```bash
whoami
nvidia-smi
pwd
ls -lah /data
```

Confirm we are:

```text
user: saurav
GPU visible
/data accessible
```

Inspect existing environments:

```bash
find /data -maxdepth 3 -type d -name "bin" 2>/dev/null | head -50
```

Also inspect:

```bash
conda env list 2>/dev/null || true
ls -lah /data
```

Reuse an appropriate existing venv if possible.

Do not destroy working Python environments.

If a new environment is required, create it under:

```bash
/data/envs/
```

For example:

```bash
python3 -m venv /data/envs/audio2face
source /data/envs/audio2face/bin/activate
```

---

# TMUX REQUIREMENT

The GPU service must survive SSH disconnects.

Run the service in tmux.

Create:

```bash
tmux new -s avatar-face
```

or detached:

```bash
tmux new-session -d -s avatar-face
```

Inside the session:

```bash
sudo -iu saurav
cd /data/<project-folder>
source <correct-venv>/bin/activate
```

Then run the persistent facial inference API.

Provide a simple way to reconnect:

```bash
tmux attach -t avatar-face
```

And inspect:

```bash
tmux ls
```

---

# NVIDIA AUDIO2FACE

Deploy NVIDIA Audio2Face-3D locally on the GPU.

Prefer the fastest real-time model suitable for live streaming.

Priority:

1. low latency
2. stable 60 FPS-capable facial output
3. correct lip sync
4. emotion-capable output
5. visual quality

Do NOT prioritize heavier diffusion quality if it introduces noticeable latency.

If both regression and diffusion variants are available, start with the lower-latency real-time variant.

Benchmark actual latency instead of assuming.

Record:

```text
audio chunk duration
inference time
face frames/sec
end-to-end face delay
GPU utilization
VRAM usage
```

---

# GPU SERVICE DESIGN

Implement a standalone persistent API service.

Recommended stack:

```text
Python
FastAPI
WebSocket
CUDA/TensorRT Audio2Face runtime
```

Suggested structure:

```text
/data/avatar_face_service/

app.py

audio2face/
    engine.py
    mappings.py

streaming/
    websocket.py
    buffering.py

schemas/
    messages.py

requirements.txt

start.sh
```

---

# API ENDPOINTS

Implement:

```text
GET /health
```

Return:

```json
{
  "status": "ok",
  "gpu": "NVIDIA H100",
  "model_loaded": true
}
```

Implement:

```text
GET /metrics
```

Return:

```json
{
  "fps": 60,
  "avg_inference_ms": 0,
  "audio_buffer_ms": 0,
  "gpu_utilization": 0,
  "vram_mb": 0
}
```

Implement:

```text
WS /ws/face
```

The WebSocket accepts streaming audio chunks.

It emits facial frames.

Example output:

```json
{
  "type": "blendshape_frame",
  "timestamp_ms": 1840,
  "weights": {
    "jawOpen": 0.61,
    "mouthFunnel": 0.18,
    "mouthPucker": 0.07,
    "mouthSmileLeft": 0.12,
    "mouthSmileRight": 0.11,
    "eyeBlinkLeft": 0.02,
    "eyeBlinkRight": 0.02
  }
}
```

Use timestamps.

The browser must interpolate frames smoothly.

---

# AUDIO PIPELINE

ElevenLabs streaming audio should be sent to BOTH:

```text
browser audio output
```

and

```text
Audio2Face GPU service
```

from the same source stream.

Conceptually:

```ts
for await (const chunk of elevenLabsStream) {
    playAudioChunk(chunk);
    faceSocket.send(chunk);
}
```

Do not separately regenerate speech for Audio2Face.

Use the exact same audio.

This is essential for synchronization.

---

# LIP SYNC MAPPING

The GLB has an ARKit-style facial rig.

Map returned Audio2Face blendshapes to the actual avatar morph target names.

Implement a config:

```ts
const morphMap = {
    jawOpen: "jawOpen",
    mouthFunnel: "mouthFunnel",
    mouthPucker: "mouthPucker",
    mouthSmileLeft: "mouthSmileLeft",
    mouthSmileRight: "mouthSmileRight",
    mouthFrownLeft: "mouthFrownLeft",
    mouthFrownRight: "mouthFrownRight",
    mouthClose: "mouthClose",
    mouthStretchLeft: "mouthStretchLeft",
    mouthStretchRight: "mouthStretchRight",
    cheekPuff: "cheekPuff",
    browInnerUp: "browInnerUp",
    browDownLeft: "browDownLeft",
    browDownRight: "browDownRight",
    eyeBlinkLeft: "eyeBlinkLeft",
    eyeBlinkRight: "eyeBlinkRight"
};
```

Inspect actual GLB names at runtime.

Do NOT silently assume exact casing if different.

Build an initialization step that prints all morph target names and creates the mapping.

---

# FACIAL COMPOSITION

Do NOT let Audio2Face own the entire face.

Final facial morph should combine:

```text
speech face
+
emotion face
+
blink
+
microexpression
```

Use weighted blending.

Example:

```ts
finalMorph =
    speechWeight * speechValue +
    emotionWeight * emotionValue +
    blinkWeight * blinkValue;
```

Clamp:

```ts
Math.min(1, Math.max(0, finalMorph));
```

Prefer speech around mouth/jaw.

Prefer emotion around:

```text
brows
eyes
cheeks
mouth corners
```

This prevents emotion from destroying lip sync.

---

# AVATAR ENGINE

Create:

```text
src/avatar/
```

with:

```text
AvatarEngine.ts

controllers/
    AnimationController.ts
    EmotionController.ts
    FaceController.ts
    GazeController.ts
    LipSyncController.ts
    LifeController.ts
    CameraDirector.ts
    WorkoutDirector.ts

state/
    AvatarState.ts
    EmotionState.ts

config/
    morphMappings.ts
    boneMappings.ts
```

Adapt paths to the current application structure.

Do not restructure unrelated code.

---

# LIFE CONTROLLER

Implement:

```ts
interface LifeState {
  breathingRate: number;
  breathingDepth: number;

  blinkRate: number;
  blinkDuration: number;

  gazeTarget: THREE.Vector3 | null;
  gazeStrength: number;

  headMicroMotion: number;

  weightShift: number;

  idleEnergy: number;
}
```

Avatar must NEVER freeze.

Always include:

```text
breathing
random blinking
tiny head motion
tiny gaze movement
weight shift
subtle torso motion
```

---

# BREATHING

Use spine/chest motion.

Do not exaggerate.

Example:

```ts
const breath =
    Math.sin(time * breathingRate);

chest.rotation.x =
    baseRotation +
    breath * breathingDepth;
```

States:

```text
calm
slow subtle

energetic
slightly faster

stressed
faster shallower

tired
slow/deeper

post exercise
fast then recover gradually
```

---

# BLINKING

Random interval:

```text
2–6 seconds
```

Allow rare double blink.

Fatigue:

```text
longer blink
slightly lowered lids
```

Stress:

```text
slightly more frequent blinking
```

Never blink periodically like a robot.

---

# GAZE

Implement realistic gaze.

States:

```text
LISTENING
mostly user

TALKING
user with occasional eye contact breaks

THINKING
brief glance away

REFERENCING_UI
look at panel

WORKOUT
look toward movement / camera appropriately

IDLE
small exploratory gaze
```

Rotate eyes before head.

Smooth with lerp/slerp.

Clamp anatomy.

Never snap.

---

# EMOTION ENGINE

Use continuous values:

```ts
interface EmotionState {
  energy: number;
  happiness: number;
  fatigue: number;
  stress: number;
  confidence: number;
  excitement: number;
  concern: number;
}
```

Maintain:

```ts
currentEmotion
targetEmotion
```

Smooth continuously.

Never switch:

```text
neutral → tired
```

instantly.

---

# USER CONDITION MIRRORING

The avatar reflects the user's condition without becoming unstable.

Example user:

```json
{
  "sleepHours": 4.0,
  "fatigue": 0.85,
  "stress": 0.65,
  "motivation": 0.4
}
```

Avatar target:

```json
{
  "energy": 0.35,
  "fatigue": 0.55,
  "concern": 0.7,
  "stress": 0.15,
  "confidence": 0.9
}
```

Rule:

```text
mirror empathy
but maintain coach confidence
```

---

# GEMINI RESPONSE FORMAT

Change Gemini output from plain text only to structured JSON.

Do not lose the conversational text.

Gemini should return:

```json
{
  "speech": "You look pretty depleted today. I'm reducing the workout volume.",

  "emotion": {
    "energy": 0.4,
    "happiness": 0.3,
    "fatigue": 0.2,
    "stress": 0.1,
    "confidence": 0.9,
    "excitement": 0.2,
    "concern": 0.7
  },

  "action": {
    "type": "POINT_PANEL"
  },

  "gaze": "workout_panel",

  "workoutAdjustment": {
    "intensityDelta": -0.3
  }
}
```

Validate Gemini JSON.

If parsing fails, fallback to:

```json
{
  "speech": "<raw text>",
  "emotion": {
    "energy": 0.5,
    "happiness": 0.5,
    "fatigue": 0,
    "stress": 0,
    "confidence": 0.8,
    "excitement": 0.3,
    "concern": 0.2
  },
  "action": {
    "type": "TALK"
  },
  "gaze": "user"
}
```

Never crash the avatar because Gemini returned malformed structure.

---

# BODY ANIMATION

Use Three.js:

```text
AnimationMixer
```

Support smooth crossfades.

Core clips:

```text
idle
listening
talking
thinking

walk
run

point_left
point_right

wave

nod
shake_head

thumbs_up
celebrate

tired_idle
confident_idle

exercise_ready
```

If animations do not exist yet, source or retarget compatible ones.

Do NOT train locomotion.

Use retargeted skeletal clips.

---

# WORKOUT DEMONSTRATIONS

First make ONE incredible exercise:

```text
SQUAT
```

Then add:

```text
RDL
LUNGE
CURL
SHOULDER PRESS
PUSH-UP
```

Do not build 50 mediocre exercises.

Each exercise should be choreography.

Example:

```ts
interface WorkoutPerformance {
  exercise: string;
  enterAnimation: string;
  exerciseAnimation: string;
  exitAnimation: string;
  repetitions: number;

  tempo?: {
    eccentric: number;
    pause: number;
    concentric: number;
  };
}
```

---

# SQUAT EXPERIENCE

When user says:

```text
Show me the squat.
```

perform:

```text
avatar looks at user
↓
nod
↓
camera widens
↓
avatar steps backward
↓
training floor activates
↓
title appears
↓
avatar enters squat stance
↓
3 controlled repetitions
↓
tempo cues
↓
form cues
↓
avatar exits
↓
walks forward
↓
camera returns
↓
continues speaking
```

---

# WORKOUT HUD

Display:

```text
BARBELL SQUAT

QUADS • GLUTES • CORE
```

During movement:

```text
3
2
1
HOLD
DRIVE
```

Add timed coaching cues:

```text
BRACE
KNEES OUT
CHEST UP
DRIVE
```

Subtle and premium.

Do not make giant cartoon text.

---

# CAMERA DIRECTOR

Create:

```text
conversation
full_body
exercise
exercise_close
dramatic_intro
```

Smooth camera transitions.

Never teleport.

---

# BODY GESTURE LAYERS

Do not stop the entire base animation just to gesture.

When possible:

```text
BASE
idle/talking

UPPER BODY
point

FACE
lip sync + emotion

GAZE
target
```

simultaneously.

---

# WALKING AND RUNNING

Walking/running should use proper animation clips.

Blend:

```text
idle → walk
walk → run
run → walk
walk → idle
```

If locomotion is in-place, translate root in code.

Do not let feet slide excessively.

For hackathon:

favor visual quality over sophisticated navigation.

---

# CONVERSATIONAL TTS

Keep ElevenLabs.

Must use streaming TTS.

Do not wait for full audio.

The avatar should begin lip sync as the first meaningful audio chunks arrive.

Audio playback and facial inference must remain synchronized.

Maintain a small jitter buffer if needed.

Ideal:

```text
20–50 ms
```

rather than hundreds of milliseconds.

---

# WEBSOCKET BUFFERING

Maintain face frame queue:

```ts
type FaceFrame = {
  timestampMs: number;
  weights: Record<string, number>;
};
```

The browser should render facial frames slightly behind audio generation if needed for perfect synchronization.

Use interpolation:

```text
frame A
↓ interpolate
frame B
```

Do not directly snap morph values per network packet.

---

# ERROR FALLBACK

If Audio2Face disconnects:

fall back immediately to procedural mouth movement.

Use:

```text
audio RMS
+
mouthOpen
+
jawOpen
```

optionally with simple vowel approximation.

The demo must never result in a motionless talking character.

Reconnect Audio2Face in background.

---

# HEALTH CHECK

Browser should query:

```text
/health
```

before conversation begins.

Show in debug panel:

```text
GPU FACE SERVICE: ONLINE
```

or:

```text
GPU FACE SERVICE: FALLBACK
```

---

# GPU START SCRIPT

Create something like:

```bash
#!/usr/bin/env bash
set -e

cd /data/avatar_face_service

source /data/envs/audio2face/bin/activate

export CUDA_VISIBLE_DEVICES=0

uvicorn app:app \
  --host 0.0.0.0 \
  --port 8765
```

Save:

```text
/data/avatar_face_service/start.sh
```

Make executable:

```bash
chmod +x /data/avatar_face_service/start.sh
```

---

# TMUX STARTUP

Provide:

```bash
tmux new-session -d -s avatar-face \
  "sudo -iu saurav bash -lc 'cd /data/avatar_face_service && ./start.sh'"
```

Verify:

```bash
tmux ls
```

Logs:

```bash
tmux capture-pane -pt avatar-face
```

Attach:

```bash
tmux attach -t avatar-face
```

---

# NETWORK EXPOSURE

Determine how the existing app reaches the NVIDIA machine.

Do NOT expose an unauthenticated GPU API publicly unless required.

Prefer:

```text
private network
SSH tunnel
authenticated reverse proxy
```

For development, SSH tunnel is acceptable:

```bash
ssh -L 8765:localhost:8765 scc
```

Then browser/backend can use:

```text
ws://localhost:8765/ws/face
```

If the app is hosted remotely, configure a secure reachable endpoint.

Use:

```text
wss://
```

in production.

---

# DEBUG PANEL

Add:

```text
Shift + D
```

Developer controls:

```text
Audio2Face connected
face FPS
inference ms
WebSocket ping
buffer delay

fatigue
stress
energy
happiness
concern
confidence

blink

gaze user
gaze panel

walk
run
point
nod

play squat
play curl
play lunge

camera modes
```

This is mandatory for fast tuning.

---

# DEMO HOTKEYS

Create safe deterministic demo controls:

```text
1 Normal
2 Tired
3 Stressed
4 Excited
5 Point
6 Walk
7 Squat Demo
8 Celebrate
```

Even if Gemini/network breaks, the judges must still see the experience.

---

# DEMO MOMENT

Optimize this sequence:

User:

```text
I'm exhausted today. I slept four hours.
```

Avatar:

- face becomes concerned
- eyes soften
- energy decreases
- head tilts
- gestures slow

Gemini responds:

```text
You're running pretty depleted today, so I'm reducing today's volume.
```

ElevenLabs starts immediately.

Avatar lip sync starts with the speech.

Workout card updates.

Avatar looks at card.

Points to it.

Then:

User:

```text
Show me the squat.
```

Avatar:

- nods
- walks backward
- camera widens
- enters workout mode
- demonstrates squat
- shows tempo
- shows coaching cues
- returns
- continues conversation

This is the core hackathon experience.

---

# PERFORMANCE TARGETS

Browser:

```text
60 FPS target
```

Face service:

```text
>= 60 facial frames/sec if possible
```

Measure inference.

Do NOT claim 2–5 ms unless benchmark confirms it.

Preferred:

```text
very small inference latency
+
stable streaming
+
minimal buffering
```

Perceived quality matters more than isolated inference timing.

---

# IMPORTANT ENGINEERING RULES

1. Keep avatar rendering entirely local in browser.
2. GPU service only returns facial control data.
3. Do not stream rendered video from GPU.
4. Do not send giant payloads.
5. Use persistent WebSocket connections.
6. Use timestamps.
7. Interpolate client-side.
8. Keep animation engine deterministic.
9. Gemini selects semantic actions only.
10. Gemini must never directly manipulate bones.
11. ElevenLabs remains the voice source.
12. Same ElevenLabs stream drives browser audio and Audio2Face.
13. Never block the render loop on network.
14. Never freeze character when backend stalls.
15. Always have fallback behavior.

---

# PRIORITY ORDER

Implement in exactly this order.

## P0 — MUST WORK

```text
GLB rendering
Audio2Face GPU service
WebSocket facial streaming
ElevenLabs streaming
lip sync
60 FPS browser
```

---

## P1 — MAKE IT ALIVE

```text
blinking
breathing
gaze
micro head movement
emotion interpolation
```

---

## P2 — BODY

```text
idle
talking
walk
run
point
nod
thumbs up
exercise stance
```

---

## P3 — WOW

```text
squat choreography
camera director
HUD
tempo
form cues
workout adaptation
```

---

## P4 — POLISH

```text
lighting
ghost rep
muscle highlight
particles
cinematic transitions
better gestures
```

---

# DO NOT SPEND TIME ON

Do not train:

```text
custom locomotion model
custom lip sync model
custom facial diffusion model
reinforcement learning
```

Do not build:

```text
50 exercises
perfect biomechanics simulation
complex cloth physics
massive gym scene
```

until the core demo is flawless.

---

# DEFINITION OF DONE

The feature is complete when:

1. GPU service launches under `saurav`.
2. It persists under tmux.
3. Model loads from `/data`.
4. `/health` works.
5. WebSocket works.
6. ElevenLabs audio streams.
7. Same audio reaches Audio2Face.
8. Blendshape frames stream back.
9. Browser maps them to GLB morph targets.
10. Avatar begins speaking without waiting for whole audio.
11. Mouth timing looks correct.
12. Emotion can coexist with speech.
13. Avatar blinks naturally.
14. Avatar breathes.
15. Avatar looks at user.
16. Avatar can look at workout UI.
17. Avatar can walk.
18. Avatar can run.
19. Avatar can gesture.
20. Avatar can demonstrate squat.
21. Workout state changes based on user condition.
22. Camera reframes automatically.
23. Debug panel exposes all important controls.
24. Demo hotkeys work.
25. Backend failures do not freeze the avatar.

---

# FINAL QUALITY STANDARD

This should NOT feel like:

```text
chatbot
+
3D skin
```

It should feel like:

```text
the coach heard me
the coach understood my physical condition
the coach reacted emotionally
the coach physically moved
the coach changed my workout
the coach showed me exactly what to do
```

The most important interaction is:

```text
LISTEN
↓
UNDERSTAND
↓
REACT
↓
SPEAK
↓
MOVE
↓
DEMONSTRATE
↓
COACH
```

Build that first.

Do not stop at architecture or placeholder code.

Inspect the existing repository, reuse what is working, implement the integration, run it, test it, fix failures, and leave the system in a runnable state.
