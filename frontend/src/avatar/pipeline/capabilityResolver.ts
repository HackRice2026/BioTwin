import type { AvatarAction, GazeMode } from "../state/AvatarState";
import type { AvatarIntent, AvatarTarget } from "./intent";
import type { MotionManifest, MotionPhase } from "./motionManifest";
import { findMotionPhase } from "./motionManifest";

export type ActiveMotionState = {
  manifest: MotionManifest;
  progress: number;
};

export type ResolvedAvatarCommand = {
  speech: string;
  action: AvatarAction;
  gaze: GazeMode;
  bodyAllowed: boolean;
  interruptRequested: boolean;
  overlay?: {
    target: AvatarTarget;
    reason: string;
  };
  phase?: MotionPhase;
};

function requestedTarget(intent: AvatarIntent): AvatarTarget {
  if (intent.target) return intent.target;
  if (intent.intent === "EXPLAIN_FORM") return "workout_panel";
  return "user";
}

function actionForIntent(intent: AvatarIntent): AvatarAction {
  if (intent.action) return intent.action;
  if (intent.intent === "DEMONSTRATE_EXERCISE" && intent.exercise === "SQUAT")
    return "squat";
  if (intent.intent === "POINT_TARGET" || intent.intent === "EXPLAIN_FORM")
    return "point";
  if (intent.intent === "WARN") return "think";
  if (intent.intent === "ENCOURAGE") return "celebrate";
  return "talk";
}

function gazeForIntent(intent: AvatarIntent): GazeMode {
  if (intent.gaze) return intent.gaze;
  if (intent.target && intent.target !== "user") return "panel";
  if (intent.intent === "DEMONSTRATE_EXERCISE") return "workout";
  return "user";
}

export function resolveAvatarIntent(
  intent: AvatarIntent,
  activeMotion?: ActiveMotionState,
): ResolvedAvatarCommand {
  const action = actionForIntent(intent);
  const gaze = gazeForIntent(intent);
  const target = requestedTarget(intent);
  if (!activeMotion) {
    return {
      speech: intent.speech,
      action,
      gaze,
      bodyAllowed: true,
      interruptRequested: false,
    };
  }

  const phase = findMotionPhase(activeMotion.manifest, activeMotion.progress);
  const wantsUpperBody =
    action === "point" || action === "celebrate" || action === "nod";
  const targetCanOverlay = phase.overlayTargets.includes(target);
  const bodyAllowed = !wantsUpperBody || phase.upperBodyGesture;
  if (bodyAllowed) {
    return {
      speech: intent.speech,
      action,
      gaze: phase.gazeOverride ? gaze : "workout",
      bodyAllowed: true,
      interruptRequested: false,
      phase,
    };
  }

  return {
    speech: intent.speech,
    action: "talk",
    gaze: phase.gazeOverride ? gaze : "workout",
    bodyAllowed: false,
    interruptRequested: !phase.safeExit,
    overlay: {
      target: targetCanOverlay ? target : "workout_panel",
      reason: `${action} blocked during ${phase.name}; using HUD overlay`,
    },
    phase,
  };
}
