import type { AvatarTarget, ExerciseName } from "./intent";

export type MotionPhaseName =
  | "SETUP"
  | "ECCENTRIC"
  | "BOTTOM"
  | "CONCENTRIC"
  | "RECOVER"
  | "EXIT";

export type MotionPhase = {
  name: MotionPhaseName;
  from: number;
  to: number;
  safeExit: boolean;
  upperBodyGesture: boolean;
  headOverride: boolean;
  gazeOverride: boolean;
  overlayTargets: AvatarTarget[];
};

export type MotionManifest = {
  id: string;
  exercise: ExerciseName;
  clip: string;
  defaultTempo: {
    eccentric: number;
    pause: number;
    concentric: number;
  };
  phases: MotionPhase[];
};

export const squatBodyweightManifest: MotionManifest = {
  id: "squat.bodyweight.v1",
  exercise: "SQUAT",
  clip: "/assets/motion/squat_bodyweight.glb",
  defaultTempo: {
    eccentric: 3,
    pause: 1,
    concentric: 1,
  },
  phases: [
    {
      name: "SETUP",
      from: 0,
      to: 0.16,
      safeExit: true,
      upperBodyGesture: true,
      headOverride: true,
      gazeOverride: true,
      overlayTargets: ["feet", "hips", "spine"],
    },
    {
      name: "ECCENTRIC",
      from: 0.16,
      to: 0.54,
      safeExit: false,
      upperBodyGesture: false,
      headOverride: true,
      gazeOverride: true,
      overlayTargets: ["knees", "hips", "spine"],
    },
    {
      name: "BOTTOM",
      from: 0.54,
      to: 0.66,
      safeExit: false,
      upperBodyGesture: false,
      headOverride: true,
      gazeOverride: true,
      overlayTargets: ["knees", "hips", "spine"],
    },
    {
      name: "CONCENTRIC",
      from: 0.66,
      to: 0.92,
      safeExit: false,
      upperBodyGesture: false,
      headOverride: true,
      gazeOverride: true,
      overlayTargets: ["knees", "hips", "spine", "breathing"],
    },
    {
      name: "RECOVER",
      from: 0.92,
      to: 1,
      safeExit: true,
      upperBodyGesture: true,
      headOverride: true,
      gazeOverride: true,
      overlayTargets: ["workout_panel", "readiness_score"],
    },
  ],
};

export function findMotionPhase(
  manifest: MotionManifest,
  progress: number,
): MotionPhase {
  const normalized = Math.min(1, Math.max(0, progress));
  return (
    manifest.phases.find(
      (phase) => normalized >= phase.from && normalized <= phase.to,
    ) ?? manifest.phases[manifest.phases.length - 1]
  );
}

export function tempoScale(
  manifest: MotionManifest,
  tempo = manifest.defaultTempo,
) {
  const planned =
    manifest.defaultTempo.eccentric +
    manifest.defaultTempo.pause +
    manifest.defaultTempo.concentric;
  const requested = tempo.eccentric + tempo.pause + tempo.concentric;
  return planned > 0 && requested > 0 ? planned / requested : 1;
}
