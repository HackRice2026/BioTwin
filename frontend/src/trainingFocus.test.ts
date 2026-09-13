import { describe, expect, it } from "vitest";
import type { TrainingDecision } from "./api";
import { spokenFocus, wantsComparison } from "./trainingFocus";

const decision = {
  available: true,
  timezone: "America/Chicago",
  curve: [{ time: "2026-09-14T12:00:00-05:00", minutes: 0, value: 60, confidence: "High", method: "measured" }],
  window: {
    start: "2026-09-14T17:40:00-05:00",
    end: "2026-09-14T18:35:00-05:00",
  },
  risks: [
    {
      start: "2026-09-14T14:00:00-05:00",
      end: "2026-09-14T16:00:00-05:00",
      label: "High-load window",
      reasons: [],
    },
  ],
} as unknown as TrainingDecision;

describe("spokenFocus", () => {
  it("highlights the best window when its time is said", () => {
    expect(spokenFocus("Your best window is around 5:40 PM.", decision)).toEqual({ kind: "window" });
  });

  it("follows the most recent mention as speech progresses", () => {
    const text = "5:40 PM is your window. Your meetings make 2 PM a bad option";
    expect(spokenFocus(text, decision)).toEqual({ kind: "risk", index: 0 });
  });

  it("brings a scenario forward when a choice is named", () => {
    expect(spokenFocus("You can train now, but waiting is better", decision)).toEqual({
      kind: "scenario",
      key: "best",
    });
  });

  it("ignores times outside anything on the timeline", () => {
    expect(spokenFocus("You slept until 7 AM.", decision)).toBeNull();
  });
});

describe("wantsComparison", () => {
  it("opens future paths only for what-if style questions", () => {
    expect(wantsComparison("What if I train now?")).toBe(true);
    expect(wantsComparison("How did I sleep?")).toBe(false);
  });
});
