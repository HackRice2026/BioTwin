export type ActivityState =
  | "IDLE"
  | "EXERTION_RISING"
  | "EXERCISING"
  | "EXERTION_FALLING"
  | "FATIGUED"
  | "RECOVERING"
  | "RESTORED";
export type MotionInput = {
  exertion: number;
  fatigue: number;
  recovery_progress: number;
};
export const transitions: {
  from: ActivityState;
  to: ActivityState;
  test: (d: MotionInput, seconds: number) => boolean;
  crossfade: number;
}[] = [
  {
    from: "IDLE",
    to: "EXERTION_RISING",
    test: (d) => d.exertion > 0.25,
    crossfade: 0.4,
  },
  {
    from: "EXERTION_RISING",
    to: "EXERCISING",
    test: (d, s) => d.exertion > 0.6 && s >= 5,
    crossfade: 0.3,
  },
  {
    from: "EXERTION_RISING",
    to: "IDLE",
    test: (d) => d.exertion < 0.2,
    crossfade: 0.5,
  },
  {
    from: "EXERCISING",
    to: "EXERTION_FALLING",
    test: (d) => d.exertion < 0.5,
    crossfade: 0.5,
  },
  {
    from: "EXERTION_FALLING",
    to: "FATIGUED",
    test: (_, s) => s >= 2,
    crossfade: 0.7,
  },
  {
    from: "FATIGUED",
    to: "RECOVERING",
    test: (d, s) => d.recovery_progress > 0.2 && s >= 60,
    crossfade: 0.9,
  },
  {
    from: "RECOVERING",
    to: "RESTORED",
    test: (d) => d.recovery_progress > 0.9,
    crossfade: 1.2,
  },
  { from: "RESTORED", to: "IDLE", test: (_, s) => s >= 5, crossfade: 1.2 },
  ...(
    [
      "EXERTION_FALLING",
      "FATIGUED",
      "RECOVERING",
      "RESTORED",
    ] as ActivityState[]
  ).map((from) => ({
    from,
    to: "EXERTION_RISING" as ActivityState,
    test: (d: MotionInput) => d.exertion > 0.6,
    crossfade: 0.4,
  })),
];
export class AvatarFSM {
  state: ActivityState = "IDLE";
  entered = 0;
  crossfade = 0.5;
  update(d: MotionInput, time: number) {
    const transition = transitions.find(
      (t) => t.from === this.state && t.test(d, time - this.entered),
    );
    if (transition) {
      this.state = transition.to;
      this.entered = time;
      this.crossfade = transition.crossfade;
    }
    return this.state;
  }
}
