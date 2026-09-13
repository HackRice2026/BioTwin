import type { TrainingDecision } from "./api";
import type { CaptionWord } from "./captions";

export type Focus =
  | { kind: "window" }
  | { kind: "risk"; index: number }
  | { kind: "scenario"; key: "now" | "best" | "rest" }
  | null;

const SPOKEN_TIME = /\b(1[0-2]|0?[1-9])(?::([0-5]\d))?\s*([ap])\.?\s?m\b/gi;

export function minutesOfDay(iso: string, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
    timeZone,
  }).formatToParts(new Date(iso));
  const part = (type: string) =>
    Number(parts.find((p) => p.type === type)?.value ?? 0);
  return part("hour") * 60 + part("minute");
}

export function spokenSoFar(words: CaptionWord[], time: number) {
  return words
    .filter((w) => w.start <= time)
    .map((w) => w.text)
    .join(" ");
}

/** Whatever the coach mentioned most recently -- a time inside the best window or a
    high-load stretch, or a train-now / wait / rest choice -- so the matching part of
    the day can be highlighted while it is being said. */
export function spokenFocus(
  text: string,
  decision: TrainingDecision | null,
): Focus {
  if (!text || !decision?.curve?.length) return null;
  const latest: { at: number; focus: Focus } = { at: -1, focus: null };
  const consider = (at: number, focus: Focus) => {
    if (at >= latest.at) Object.assign(latest, { at, focus });
  };
  const tz = decision.timezone;
  for (const match of text.matchAll(SPOKEN_TIME)) {
    const hour =
      (Number(match[1]) % 12) + (match[3].toLowerCase() === "p" ? 12 : 0);
    const said = hour * 60 + Number(match[2] ?? 0);
    if (decision.available) {
      const start = minutesOfDay(decision.window.start, tz);
      const end = minutesOfDay(decision.window.end, tz);
      if (said >= start - 10 && said <= end) {
        consider(match.index ?? 0, { kind: "window" });
        continue;
      }
    }
    (decision.risks ?? []).forEach((risk, index) => {
      if (
        said >= minutesOfDay(risk.start, tz) &&
        said < minutesOfDay(risk.end, tz)
      )
        consider(match.index ?? 0, { kind: "risk", index });
    });
  }
  const choices: [RegExp, Focus][] = [
    [/\btrain(?:ing)? (?:right )?now\b/gi, { kind: "scenario", key: "now" }],
    [/\bwait(?:ing)?\b/gi, { kind: "scenario", key: "best" }],
    [/\b(?:rest|resting|skip)\b/gi, { kind: "scenario", key: "rest" }],
  ];
  for (const [pattern, focus] of choices)
    for (const match of text.matchAll(pattern))
      consider(match.index ?? 0, focus);
  return latest.focus;
}

export function wantsComparison(question: string) {
  return /\bwhat if\b|\btrain(?:ing)? (?:right )?now\b|\binstead\b|\bshould i (?:wait|rest|skip)\b|\bcompare\b|\brest\b/i.test(
    question,
  );
}
