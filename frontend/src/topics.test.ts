import { describe, it, expect } from "vitest";
import { questionTopic, questionScenario } from "./topics";
import { CaptionTimeline } from "./captions";
describe("question routing", () => {
  it.each([
    ["What is my heart rate?", "heart"],
    ["How did I sleep?", "sleep"],
    ["How many calories did I burn?", "calories"],
    ["How many steps today?", "steps"],
    ["When should I workout today?", "plan"],
    ["What if I walk instead of sleep?", "what-if"],
    ["Why am I tired?", "recovery"],
    ["Hi there", null],
    ["What is your name?", null],
  ])("%s → %s", (question, topic) =>
    expect(questionTopic(question)).toBe(topic),
  );
  it("selects the requested scenario", () => {
    expect(questionScenario("What if I rest?")).toBe("rest");
    expect(questionScenario("What if I walk?")).toBe("light");
    expect(questionScenario("What if I exercise?")).toBe("exercise");
  });
});
describe("speech captions", () => {
  it("keeps split words and absolute stream timings on the playback timeline", () => {
    const timeline = new CaptionTimeline();
    timeline.append({
      characters: ["H", "e"],
      character_start_times_seconds: [0, 0.1],
      character_end_times_seconds: [0.1, 0.2],
    });
    timeline.append({
      characters: ["y", " ", "y", "o", "u"],
      character_start_times_seconds: [0.2, 0.3, 0.4, 0.5, 0.6],
      character_end_times_seconds: [0.3, 0.4, 0.5, 0.6, 0.7],
    });
    const words = timeline.words();
    expect(words.map((w) => w.text)).toEqual(["Hey", "you"]);
    expect(words[1].start).toBeCloseTo(0.4);
    expect(words[1].end).toBeCloseTo(0.7);
  });
  it("rejects malformed timing rather than inventing captions", () => {
    expect(() =>
      new CaptionTimeline().append({
        characters: ["a"],
        character_start_times_seconds: [],
        character_end_times_seconds: [],
      }),
    ).toThrow();
  });
});
