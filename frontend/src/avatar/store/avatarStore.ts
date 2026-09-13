import { create } from "zustand";
import type { AvatarEmotion, AvatarPipeline } from "../../contracts";
import type { AvatarSemanticState } from "../state/AvatarState";
import { defaultAvatarState, defaultEmotion } from "../state/AvatarState";
import {
  resolveAvatarIntent,
  type ResolvedAvatarCommand,
} from "../pipeline/capabilityResolver";
import {
  findMotionPhase,
  squatBodyweightManifest,
  type MotionManifest,
  type MotionPhaseName,
} from "../pipeline/motionManifest";
import {
  normalizeAvatarIntent,
  type AvatarIntent,
  type AvatarTarget,
} from "../pipeline/intent";

export type AvatarMode = "CONVERSATION" | "EXERCISE" | "TRANSITION";

export type ActiveHud = {
  target: AvatarTarget;
  text: string;
  reason?: string;
};

type AvatarStoreState = {
  mode: AvatarMode;
  activePhase: MotionPhaseName | null;
  activeProgress: number;
  activeManifest: MotionManifest | null;
  currentIntent: AvatarIntent | null;
  currentCommand: ResolvedAvatarCommand | null;
  activeHud: ActiveHud | null;
  semantic: AvatarSemanticState;
  applyAvatarPayload: (payload: AvatarPipeline | null | undefined) => void;
  setExercise: (manifest?: MotionManifest | null) => void;
  setPhase: (phaseId: MotionPhaseName | null) => void;
  clearHud: () => void;
  resetAvatarResolver: () => void;
};

function packetWantsSquat(payload: AvatarPipeline | null | undefined) {
  return (
    payload?.body?.deterministic_motion === squatBodyweightManifest.id ||
    payload?.body?.semantic_action === "squat" ||
    payload?.fallback?.intent?.exercise === "SQUAT"
  );
}

function progressForPhase(manifest: MotionManifest, phaseId: MotionPhaseName) {
  const phase = manifest.phases.find((candidate) => candidate.name === phaseId);
  return phase ? (phase.from + phase.to) / 2 : 0;
}

function cleanEmotion(
  emotion?: AvatarEmotion | Partial<AvatarSemanticState["emotion"]>,
) {
  const cleaned: Partial<AvatarSemanticState["emotion"]> = {};
  if (!emotion) return cleaned;
  for (const key of [
    "energy",
    "happiness",
    "fatigue",
    "stress",
    "confidence",
    "excitement",
    "concern",
  ] as const) {
    const value = emotion[key];
    if (typeof value === "number") cleaned[key] = value;
  }
  return cleaned;
}

function packetHud(payload: AvatarPipeline | null | undefined): ActiveHud | null {
  const target = payload?.fallback?.hud_target;
  if (
    target !== "knees" &&
    target !== "hips" &&
    target !== "spine" &&
    target !== "feet" &&
    target !== "breathing" &&
    target !== "workout_panel" &&
    target !== "readiness_score" &&
    target !== "heart_rate_chart" &&
    target !== "user"
  ) {
    return null;
  }
  return {
    target,
    text: payload?.fallback?.hud_text || "Coach cue",
  };
}

function resolvePacket(
  payload: AvatarPipeline | null | undefined,
  manifest: MotionManifest | null,
  progress: number,
) {
  const intent = normalizeAvatarIntent(payload?.fallback?.intent);
  const activeMotion = manifest ? { manifest, progress } : undefined;
  const command = resolveAvatarIntent(intent, activeMotion);
  const hud = command.overlay
    ? {
        target: command.overlay.target,
        text: payload?.fallback?.hud_text || command.speech || command.overlay.reason,
        reason: command.overlay.reason,
      }
    : packetHud(payload);
  return { intent, command, hud };
}

function semanticForPacket(
  payload: AvatarPipeline | null | undefined,
  intent: AvatarIntent,
  command: ResolvedAvatarCommand,
): AvatarSemanticState {
  const deterministic = payload?.body?.deterministic_motion;
  const action =
    command.bodyAllowed === false
      ? command.action
      : (payload?.body?.semantic_action ??
        command.action ??
        intent.action ??
        (deterministic === squatBodyweightManifest.id ? "squat" : "talk"));
  return {
    emotion: {
      ...defaultEmotion,
      ...cleanEmotion(intent.emotion),
      ...cleanEmotion(payload?.face?.emotion),
    },
    action,
    gaze: payload?.face?.gaze ?? command.gaze ?? intent.gaze ?? "user",
    camera:
      deterministic && deterministic !== "none"
        ? "exercise"
        : action === "walk" || action === "run"
          ? "full_body"
          : "conversation",
  };
}

export const useAvatarStore = create<AvatarStoreState>((set, get) => ({
  mode: "CONVERSATION",
  activePhase: null,
  activeProgress: 0,
  activeManifest: null,
  currentIntent: null,
  currentCommand: null,
  activeHud: null,
  semantic: defaultAvatarState,

  applyAvatarPayload: (payload) => {
    const nextManifest = packetWantsSquat(payload)
      ? squatBodyweightManifest
      : get().activeManifest;
    const mode = nextManifest ? "EXERCISE" : "CONVERSATION";
    const { intent, command, hud } = resolvePacket(
      payload,
      mode === "EXERCISE" ? nextManifest : null,
      get().activeProgress,
    );
    set({
      mode,
      activeManifest: nextManifest,
      currentIntent: intent,
      currentCommand: command,
      activeHud: hud,
      semantic: semanticForPacket(payload, intent, command),
    });
  },

  setExercise: (manifest = squatBodyweightManifest) => {
    set({
      mode: manifest ? "EXERCISE" : "CONVERSATION",
      activeManifest: manifest,
      activePhase: manifest ? get().activePhase : null,
      activeProgress: manifest ? get().activeProgress : 0,
    });
  },

  setPhase: (phaseId) => {
    const manifest = get().activeManifest ?? squatBodyweightManifest;
    if (!phaseId) {
      set({
        mode: "CONVERSATION",
        activePhase: null,
        activeProgress: 0,
        activeManifest: null,
        activeHud: null,
      });
      return;
    }
    const progress = progressForPhase(manifest, phaseId);
    const phase = findMotionPhase(manifest, progress);
    set({
      mode: "EXERCISE",
      activeManifest: manifest,
      activePhase: phase.name,
      activeProgress: progress,
    });
  },

  clearHud: () => set({ activeHud: null }),

  resetAvatarResolver: () =>
    set({
      mode: "CONVERSATION",
      activePhase: null,
      activeProgress: 0,
      activeManifest: null,
      currentIntent: null,
      currentCommand: null,
      activeHud: null,
      semantic: defaultAvatarState,
    }),
}));
