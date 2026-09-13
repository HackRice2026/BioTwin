import { beforeEach, describe, expect, it } from "vitest";
import { useAvatarStore } from "./avatarStore";

const kneesCue = {
  face: {
    speech_text: "Keep your knees tracking out.",
    gaze: "panel" as const,
  },
  body: {
    semantic_action: "point" as const,
    deterministic_motion: "squat.bodyweight.v1" as const,
  },
  fallback: {
    intent: {
      intent: "EXPLAIN_FORM" as const,
      speech: "Keep your knees tracking out.",
      target: "knees" as const,
      action: "point" as const,
    },
    hud_target: "knees" as const,
    hud_text: "Knees out",
    resolver_mode: "hud_overlay" as const,
  },
};

describe("avatar resolver store", () => {
  beforeEach(() => {
    useAvatarStore.getState().resetAvatarResolver();
  });

  it("turns locked squat gestures into HUD overlays", () => {
    useAvatarStore.getState().setPhase("ECCENTRIC");
    useAvatarStore.getState().applyAvatarPayload(kneesCue);

    const state = useAvatarStore.getState();
    expect(state.mode).toBe("EXERCISE");
    expect(state.activeHud).toMatchObject({
      target: "knees",
      text: "Knees out",
    });
    expect(state.currentCommand?.bodyAllowed).toBe(false);
    expect(state.semantic.action).toBe("talk");
    expect(state.semantic.camera).toBe("exercise");
  });

  it("allows physical gestures during setup without a HUD fallback", () => {
    useAvatarStore.getState().setPhase("SETUP");
    useAvatarStore.getState().applyAvatarPayload({
      ...kneesCue,
      fallback: {
        ...kneesCue.fallback,
        hud_target: undefined,
      },
    });

    const state = useAvatarStore.getState();
    expect(state.currentCommand?.bodyAllowed).toBe(true);
    expect(state.activeHud).toBeNull();
    expect(state.currentCommand?.action).toBe("point");
  });
});
