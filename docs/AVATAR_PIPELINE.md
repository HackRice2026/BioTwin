# Avatar Pipeline Fallback

Branch: `semantic-avatar-fallback`

Status: deterministic fallback pivot wired through the frontend resolver store.

## Why this branch exists

The generative audio-to-motion path is not reliable enough for a domain-specific fitness coach. EMAGE-style output can be useful research, but blind retargeting from SMPL-X-style motion onto our custom browser GLB produced the exact risks we care about avoiding:

- coordinate/rest-pose mismatch
- unstable limbs and collapsed poses
- no semantic awareness of what the coach is doing
- mushy biomechanics for exercises that require precise form
- unsafe blending between generated upper-body motion and deterministic exercise motion

This branch starts the safer architecture: a layered semantic state machine. The LLM is the director, not the animator. Body motion should come from validated clips/manifests, face motion from ARKit morphs/visemes, and gaze/HUD behavior from deterministic rules.

## Done in this branch

- Added typed avatar intent contracts in `frontend/src/avatar/pipeline/intent.ts`.
- Added typed motion-manifest contracts and a starter squat manifest in `frontend/src/avatar/pipeline/motionManifest.ts`.
- Added a capability resolver in `frontend/src/avatar/pipeline/capabilityResolver.ts`.
- Added tests proving that blocked physical gestures become HUD overlays during locked exercise phases.
- Wired Gemini narration to request and return one `avatar` packet alongside the guarded text answer.
- The `avatar` packet now carries data for all three tracks:
  - `face`: grounded speech text, ARKit emotion values, gaze target, preferred face backend.
  - `body`: semantic body action, EMAGE enable flag, deterministic motion id, tempo, safe-exit flag.
  - `fallback`: strict semantic intent, HUD target/text, resolver mode.
- Persisted `avatar` JSON on conversations and returns it from `/api/twin/ask` and transcript history.
- Added `frontend/src/avatar/store/avatarStore.ts`, a Zustand resolver store that keeps the current manifest phase, normalized backend intent, resolved command, semantic avatar state, and HUD fallback state in one place.
- Frontend now applies `reply.avatar` through the Zustand resolver before emitting to the avatar event bus, so Gemini state drives face/gaze/body/fallback behavior through one arbitration layer.
- `Avatar.tsx` now publishes procedural squat phase changes into the resolver store using `squat.bodyweight.v1`.
- Blocked resolver gestures now render as Drei `<Html>` HUD cues anchored near semantic GLB targets such as knees, hips, spine, feet, and workout panel locations.
- Added store tests proving locked squat phases route blocked pointing into HUD overlays while setup phases still allow physical gestures.

## What this branch does not do yet

- It does not replace the current `Avatar.tsx` render loop; the store is wired around the existing procedural squat loop.
- It does not author or import mocap clips.
- It does not touch skeletal bone math.
- It does not remove the existing face/lip-sync fallback service.
- It does not implement safe-exit handoff yet; blocked gestures become HUD overlays immediately.

## Current intended flow

```text
Gemini strict JSON intent
  -> validate/normalize AvatarIntent
  -> Capability Resolver checks active motion phase
  -> allowed body actions go to animation layer
  -> blocked gestures become HUD overlays anchored to semantic targets
  -> face/gaze/emotion continue independently
```

## Next steps

1. Replace procedural squat bones with a real validated squat animation clip and the `squat.bodyweight.v1` manifest.
2. Add manifest sidecar loading from `public/assets/motion/*.json` instead of the inline starter manifest.
3. Implement safe-exit handoff:
   - mark `interruptRequested`
   - wait for the next manifest phase with `safeExit: true`
   - crossfade to conversational idle
4. Add pending-intent replay after safe exit so `safe_exit_then_act` can perform the original gesture once the body is no longer locked.
5. Keep ARKit face, blink, gaze, and voice paths independent of body animation.

## Rule for future work

Do not let an LLM or audio model directly manipulate bones. It may request semantic intent only. The resolver decides whether that intent becomes body animation, face/gaze behavior, or a HUD overlay.
