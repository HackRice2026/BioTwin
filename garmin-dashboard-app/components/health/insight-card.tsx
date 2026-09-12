import { Sparkles } from "lucide-react";

/**
 * Static placeholder for the planned AI-insight panel (designdoc.md §8).
 * Wire an actual model into `body` as a follow-up -- the slot and styling
 * are the deliverable for now.
 */
export function InsightCard({ body }: { body: string }) {
  return (
    <div className="rounded-3xl border border-amber/25 bg-gradient-to-br from-amber-fill/60 to-card p-5">
      <div className="flex items-center gap-2 text-amber">
        <Sparkles size={16} strokeWidth={2} />
        <span className="text-xs font-semibold uppercase tracking-wider">
          Insight
        </span>
      </div>
      <p className="mt-2 text-sm leading-relaxed text-foreground">{body}</p>
    </div>
  );
}
