import * as THREE from "three";
import type {
  AvatarSemanticState,
  BodyFrame,
  FaceFrame,
} from "./state/AvatarState";

const audioEvent = "biotwin:avatar-audio";
const semanticEvent = "biotwin:avatar-semantic";

export type AvatarAudioPayload = {
  bytes: ArrayBuffer;
  timestampMs: number;
};

function canUseWindow() {
  return typeof window !== "undefined";
}

export function emitAvatarAudio(bytes: ArrayBuffer) {
  if (!canUseWindow()) return;
  window.dispatchEvent(
    new CustomEvent<AvatarAudioPayload>(audioEvent, {
      detail: { bytes, timestampMs: performance.now() },
    }),
  );
}

export function listenAvatarAudio(
  handler: (payload: AvatarAudioPayload) => void,
) {
  if (!canUseWindow()) return () => {};
  const listener = (event: Event) =>
    handler((event as CustomEvent<AvatarAudioPayload>).detail);
  window.addEventListener(audioEvent, listener);
  return () => window.removeEventListener(audioEvent, listener);
}

export function emitAvatarSemantic(next: Partial<AvatarSemanticState>) {
  if (!canUseWindow()) return;
  window.dispatchEvent(new CustomEvent(semanticEvent, { detail: next }));
}

export function listenAvatarSemantic(
  handler: (payload: Partial<AvatarSemanticState>) => void,
) {
  if (!canUseWindow()) return () => {};
  const listener = (event: Event) =>
    handler((event as CustomEvent<Partial<AvatarSemanticState>>).detail);
  window.addEventListener(semanticEvent, listener);
  return () => window.removeEventListener(semanticEvent, listener);
}

export function parseFaceFrame(payload: unknown): FaceFrame | null {
  if (!payload || typeof payload !== "object") return null;
  const data = payload as Record<string, unknown>;
  if (data.type && data.type !== "blendshape_frame") return null;
  if (!data.weights || typeof data.weights !== "object") return null;
  return {
    timestampMs:
      typeof data.timestamp_ms === "number"
        ? data.timestamp_ms
        : typeof data.timestampMs === "number"
          ? data.timestampMs
          : performance.now(),
    weights: data.weights as Record<string, number>,
  };
}

export function parseBodyFrame(payload: unknown): BodyFrame | null {
  if (!payload || typeof payload !== "object") return null;
  const data = payload as Record<string, unknown>;
  if (data.type && data.type !== "body_frame") return null;
  if (!data.bones || typeof data.bones !== "object") return null;
  return {
    timestampMs:
      typeof data.timestamp_ms === "number" ? data.timestamp_ms : performance.now(),
    bones: data.bones as Record<string, [number, number, number]>,
  };
}

// axis-angle vector [x, y, z] (direction = axis, magnitude = angle in
// radians) -> THREE.Quaternion. The body service already negates its output
// to match this rig's convention (see docs/AVATAR_IMPLEMENTATION_PLAN.md,
// "Body gestures" -- empirically determined, not derived analytically), so
// this is a plain, un-adjusted conversion.
export function axisAngleToQuaternion(aa: [number, number, number]): THREE.Quaternion {
  const angle = Math.sqrt(aa[0] * aa[0] + aa[1] * aa[1] + aa[2] * aa[2]);
  if (angle < 1e-8) return new THREE.Quaternion();
  const axis = new THREE.Vector3(aa[0] / angle, aa[1] / angle, aa[2] / angle);
  return new THREE.Quaternion().setFromAxisAngle(axis, angle);
}
