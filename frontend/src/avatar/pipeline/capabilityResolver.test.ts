import { describe, expect, it } from "vitest";
import { resolveAvatarIntent } from "./capabilityResolver";
import { normalizeAvatarIntent } from "./intent";
import { findMotionPhase, squatBodyweightManifest, tempoScale } from "./motionManifest";

describe("semantic avatar fallback resolver", () => {
  it("normalizes malformed LLM intent into a safe talking fallback", () => {
    const intent = normalizeAvatarIntent({
      intent: "SPIN_LIMBS",
      speech: 42,
      action: "helicopter",
      emotion: { energy: 4, stress: -1, concern: 0.4 },
    });
    expect(intent.intent).toBe("ANSWER");
    expect(intent.speech).toBe("");
    expect(intent.action).toBe("talk");
    expect(intent.gaze).toBe("user");
    expect(intent.emotion).toEqual({ energy: 1, stress: 0, concern: 0.4 });
  });

  it("allows physical pointing during setup", () => {
    const intent = normalizeAvatarIntent({
      intent: "POINT_TARGET",
      speech: "Start with your feet here.",
      target: "feet",
    });
    const command = resolveAvatarIntent(intent, {
      manifest: squatBodyweightManifest,
      progress: 0.08,
    });
    expect(command.bodyAllowed).toBe(true);
    expect(command.action).toBe("point");
    expect(command.overlay).toBeUndefined();
  });

  it("turns blocked gestures into semantic HUD overlays during locked squat phases", () => {
    const intent = normalizeAvatarIntent({
      intent: "EXPLAIN_FORM",
      speech: "Keep your knees tracking out.",
      target: "knees",
      action: "point",
    });
    const command = resolveAvatarIntent(intent, {
      manifest: squatBodyweightManifest,
      progress: 0.58,
    });
    expect(command.bodyAllowed).toBe(false);
    expect(command.action).toBe("talk");
    expect(command.interruptRequested).toBe(true);
    expect(command.overlay).toEqual({
      target: "knees",
      reason: "point blocked during BOTTOM; using HUD overlay",
    });
  });

  it("uses normalized manifest progress instead of hardcoded seconds", () => {
    expect(findMotionPhase(squatBodyweightManifest, 0.55).name).toBe("BOTTOM");
    expect(findMotionPhase(squatBodyweightManifest, 0.93).safeExit).toBe(true);
  });

  it("computes tempo scaling against the manifest's default tempo", () => {
    expect(
      tempoScale(squatBodyweightManifest, {
        eccentric: 6,
        pause: 2,
        concentric: 2,
      }),
    ).toBeCloseTo(0.5);
  });
});
