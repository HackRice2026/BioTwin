import type {
  AvatarAction,
  EmotionState,
  GazeMode,
} from "../state/AvatarState";

export type AvatarIntentName =
  | "ANSWER"
  | "EXPLAIN_FORM"
  | "DEMONSTRATE_EXERCISE"
  | "ADJUST_WORKOUT"
  | "POINT_TARGET"
  | "ENCOURAGE"
  | "WARN"
  | "IDLE";

export type AvatarTarget =
  | "user"
  | "workout_panel"
  | "readiness_score"
  | "heart_rate_chart"
  | "knees"
  | "hips"
  | "spine"
  | "feet"
  | "breathing";

export type ExerciseName =
  | "NONE"
  | "SQUAT"
  | "RDL"
  | "LUNGE"
  | "CURL"
  | "SHOULDER_PRESS"
  | "PUSH_UP";

export type CoachTone =
  | "calm"
  | "encouraging"
  | "concerned"
  | "confident"
  | "urgent";

export type WorkoutTempo = {
  eccentric: number;
  pause: number;
  concentric: number;
};

export type WorkoutAdjustment = {
  intensityDelta?: number;
  volumeDelta?: number;
  reason?: string;
};

export type AvatarIntent = {
  intent: AvatarIntentName;
  speech: string;
  target?: AvatarTarget;
  exercise?: ExerciseName;
  action?: AvatarAction;
  gaze?: GazeMode;
  tone?: CoachTone;
  emotion?: Partial<EmotionState>;
  tempo?: WorkoutTempo;
  workoutAdjustment?: WorkoutAdjustment;
};

const validIntents = new Set<AvatarIntentName>([
  "ANSWER",
  "EXPLAIN_FORM",
  "DEMONSTRATE_EXERCISE",
  "ADJUST_WORKOUT",
  "POINT_TARGET",
  "ENCOURAGE",
  "WARN",
  "IDLE",
]);

const validTargets = new Set<AvatarTarget>([
  "user",
  "workout_panel",
  "readiness_score",
  "heart_rate_chart",
  "knees",
  "hips",
  "spine",
  "feet",
  "breathing",
]);

const validExercises = new Set<ExerciseName>([
  "NONE",
  "SQUAT",
  "RDL",
  "LUNGE",
  "CURL",
  "SHOULDER_PRESS",
  "PUSH_UP",
]);

const validActions = new Set<AvatarAction>([
  "idle",
  "talk",
  "listen",
  "think",
  "point",
  "walk",
  "run",
  "nod",
  "celebrate",
  "squat",
]);

const validGazes = new Set<GazeMode>(["user", "panel", "away", "workout"]);
const validTones = new Set<CoachTone>([
  "calm",
  "encouraging",
  "concerned",
  "confident",
  "urgent",
]);

function numberOrUndefined(value: unknown): number | undefined {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function stringOrUndefined(value: unknown): string | undefined {
  return typeof value === "string" ? value : undefined;
}

function bounded(value: unknown) {
  const parsed = numberOrUndefined(value);
  if (parsed == null) return undefined;
  return Math.min(1, Math.max(0, parsed));
}

function normalizeEmotion(value: unknown): Partial<EmotionState> | undefined {
  if (!value || typeof value !== "object") return undefined;
  const source = value as Record<string, unknown>;
  const emotion: Partial<EmotionState> = {};
  for (const key of [
    "energy",
    "happiness",
    "fatigue",
    "stress",
    "confidence",
    "excitement",
    "concern",
  ] as const) {
    const next = bounded(source[key]);
    if (next != null) emotion[key] = next;
  }
  return Object.keys(emotion).length ? emotion : undefined;
}

function normalizeTempo(value: unknown): WorkoutTempo | undefined {
  if (!value || typeof value !== "object") return undefined;
  const source = value as Record<string, unknown>;
  const eccentric = numberOrUndefined(source.eccentric);
  const pause = numberOrUndefined(source.pause);
  const concentric = numberOrUndefined(source.concentric);
  if (eccentric == null || pause == null || concentric == null) return undefined;
  return {
    eccentric: Math.max(0.5, eccentric),
    pause: Math.max(0, pause),
    concentric: Math.max(0.5, concentric),
  };
}

function normalizeAdjustment(value: unknown): WorkoutAdjustment | undefined {
  if (!value || typeof value !== "object") return undefined;
  const source = value as Record<string, unknown>;
  const adjustment: WorkoutAdjustment = {};
  const intensityDelta = numberOrUndefined(source.intensityDelta);
  const volumeDelta = numberOrUndefined(source.volumeDelta);
  if (intensityDelta != null)
    adjustment.intensityDelta = Math.min(1, Math.max(-1, intensityDelta));
  if (volumeDelta != null)
    adjustment.volumeDelta = Math.min(1, Math.max(-1, volumeDelta));
  adjustment.reason = stringOrUndefined(source.reason);
  return Object.keys(adjustment).length ? adjustment : undefined;
}

export function normalizeAvatarIntent(input: unknown): AvatarIntent {
  if (!input || typeof input !== "object") {
    return { intent: "ANSWER", speech: "", action: "talk", gaze: "user" };
  }
  const source = input as Record<string, unknown>;
  const requestedIntent = source.intent;
  const intent =
    typeof requestedIntent === "string" &&
    validIntents.has(requestedIntent as AvatarIntentName)
      ? (requestedIntent as AvatarIntentName)
      : "ANSWER";
  const target =
    typeof source.target === "string" &&
    validTargets.has(source.target as AvatarTarget)
      ? (source.target as AvatarTarget)
      : undefined;
  const exercise =
    typeof source.exercise === "string" &&
    validExercises.has(source.exercise as ExerciseName)
      ? (source.exercise as ExerciseName)
      : undefined;
  const action =
    typeof source.action === "string" &&
    validActions.has(source.action as AvatarAction)
      ? (source.action as AvatarAction)
      : intent === "DEMONSTRATE_EXERCISE" && exercise === "SQUAT"
        ? "squat"
        : intent === "POINT_TARGET"
          ? "point"
          : "talk";
  const gaze =
    typeof source.gaze === "string" && validGazes.has(source.gaze as GazeMode)
      ? (source.gaze as GazeMode)
      : target && target !== "user"
        ? "panel"
        : "user";
  return {
    intent,
    speech: stringOrUndefined(source.speech) ?? "",
    target,
    exercise,
    action,
    gaze,
    tone:
      typeof source.tone === "string" && validTones.has(source.tone as CoachTone)
        ? (source.tone as CoachTone)
        : undefined,
    emotion: normalizeEmotion(source.emotion),
    tempo: normalizeTempo(source.tempo),
    workoutAdjustment: normalizeAdjustment(source.workoutAdjustment),
  };
}
