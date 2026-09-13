export type Topic =
  "heart" | "sleep" | "calories" | "steps" | "plan" | "recovery";
/** Match the question locally before the narration request; never inspect its answer. */
export function questionTopic(question: string): Topic | null {
  if (
    /\bplan\b|\bcalendar\b|\b(agenda|meetings?|appointments?|events?|tasks?|book|add|create)\b|\bschedul|\bremind|\bwhen\b.*\b(work ?out|exercise|nap)\b|\bfit\b.*\bwork ?out\b/i.test(
      question,
    )
  )
    return "plan";
  if (/\bheart\b|\bpulse\b|\bbpm\b|\bhrv\b/i.test(question)) return "heart";
  if (/\bsleep\b|\bslept\b|\bnap\b|\bbedtime\b/i.test(question)) return "sleep";
  if (/\bcalori|\bkcal\b|\bburn(ed|ing)?\b/i.test(question)) return "calories";
  if (/\bstep(s)?\b|\bwalk(ed|ing)?\b|\bdistance\b/i.test(question))
    return "steps";
  if (
    /\brecover|\breadiness\b|\btired\b|\benergy\b|\bbattery\b/i.test(question)
  )
    return "recovery";
  return null;
}
