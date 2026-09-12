import type { EmotionState } from "../state/AvatarState";
import { clamp01 } from "../state/AvatarState";

export const audio2FaceMorphMap: Record<string, string> = {
  browDownLeft: "browDownLeft",
  browDownRight: "browDownRight",
  browInnerUp: "browInnerUp",
  cheekPuff: "cheekPuff",
  eyeBlinkLeft: "eyeBlinkLeft",
  eyeBlinkRight: "eyeBlinkRight",
  eyeSquintLeft: "eyeSquintLeft",
  eyeSquintRight: "eyeSquintRight",
  jawOpen: "jawOpen",
  mouthClose: "mouthClose",
  mouthFrownLeft: "mouthFrownLeft",
  mouthFrownRight: "mouthFrownRight",
  mouthFunnel: "mouthFunnel",
  mouthPucker: "mouthPucker",
  mouthSmileLeft: "mouthSmileLeft",
  mouthSmileRight: "mouthSmileRight",
  mouthStretchLeft: "mouthStretchLeft",
  mouthStretchRight: "mouthStretchRight",
};

export function emotionMorphs(emotion: EmotionState): Record<string, number> {
  return {
    browInnerUp: clamp01(emotion.concern * 0.34 + emotion.excitement * 0.1),
    browDownLeft: clamp01(emotion.stress * 0.18 + emotion.fatigue * 0.08),
    browDownRight: clamp01(emotion.stress * 0.18 + emotion.fatigue * 0.08),
    cheekSquintLeft: clamp01(emotion.happiness * 0.12),
    cheekSquintRight: clamp01(emotion.happiness * 0.12),
    eyeSquintLeft: clamp01(emotion.confidence * 0.05 + emotion.fatigue * 0.12),
    eyeSquintRight: clamp01(emotion.confidence * 0.05 + emotion.fatigue * 0.12),
    mouthSmileLeft: clamp01(emotion.happiness * 0.28 + emotion.confidence * 0.08),
    mouthSmileRight: clamp01(emotion.happiness * 0.28 + emotion.confidence * 0.08),
    mouthFrownLeft: clamp01(emotion.concern * 0.12 + emotion.fatigue * 0.06),
    mouthFrownRight: clamp01(emotion.concern * 0.12 + emotion.fatigue * 0.06),
  };
}

export function mouthFallback(
  time: number,
  speaking: boolean,
  audioEnergy: number,
): Record<string, number> {
  if (!speaking) return {};
  const syllable = Math.abs(Math.sin(time * 13.5));
  const smaller = Math.abs(Math.sin(time * 21.0 + 0.6));
  const open = clamp01(0.08 + audioEnergy * 1.15 + syllable * 0.34);
  return {
    jawOpen: open,
    mouthClose: clamp01((1 - open) * 0.18),
    mouthFunnel: clamp01(smaller * 0.15 + audioEnergy * 0.16),
    mouthPucker: clamp01(Math.abs(Math.sin(time * 7.4)) * 0.12),
    mouthStretchLeft: clamp01(syllable * 0.08),
    mouthStretchRight: clamp01(syllable * 0.08),
  };
}
