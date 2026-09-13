export type GazeMode = "user" | "panel" | "away" | "workout";

export type AvatarAction =
  | "idle"
  | "talk"
  | "listen"
  | "think"
  | "point"
  | "walk"
  | "run"
  | "nod"
  | "celebrate"
  | "squat";

export type CameraMode = "conversation" | "full_body" | "exercise";

export type FaceServiceState = "checking" | "online" | "fallback";

export type EmotionState = {
  energy: number;
  happiness: number;
  fatigue: number;
  stress: number;
  confidence: number;
  excitement: number;
  concern: number;
};

export type AvatarSemanticState = {
  emotion: EmotionState;
  action: AvatarAction;
  gaze: GazeMode;
  camera: CameraMode;
};

export type FaceFrame = {
  timestampMs: number;
  weights: Record<string, number>;
};

// bones maps a bone name (e.g. "LeftArm") to an already-sign-corrected
// [x, y, z] axis-angle vector -- the delta to compose onto that bone's own
// rest quaternion, not an absolute rotation. See avatarBus.ts's
// axisAngleToQuaternion for how it's applied.
export type BodyFrame = {
  timestampMs: number;
  bones: Record<string, [number, number, number]>;
};

export const defaultEmotion: EmotionState = {
  energy: 0.55,
  happiness: 0.45,
  fatigue: 0.08,
  stress: 0.08,
  confidence: 0.82,
  excitement: 0.25,
  concern: 0.16,
};

export const defaultAvatarState: AvatarSemanticState = {
  emotion: defaultEmotion,
  action: "idle",
  gaze: "user",
  camera: "conversation",
};

export function clamp01(value: number) {
  return Math.min(1, Math.max(0, value));
}

export function blendEmotion(
  current: EmotionState,
  target: EmotionState,
  amount: number,
): EmotionState {
  return {
    energy: current.energy + (target.energy - current.energy) * amount,
    happiness: current.happiness + (target.happiness - current.happiness) * amount,
    fatigue: current.fatigue + (target.fatigue - current.fatigue) * amount,
    stress: current.stress + (target.stress - current.stress) * amount,
    confidence:
      current.confidence + (target.confidence - current.confidence) * amount,
    excitement:
      current.excitement + (target.excitement - current.excitement) * amount,
    concern: current.concern + (target.concern - current.concern) * amount,
  };
}
