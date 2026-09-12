import { Bed } from "lucide-react";
import { getSleepNights, getSummary } from "@/lib/health-data";
import { summarize, formatDay } from "@/lib/stats";
import { DetailHeader } from "@/components/health/detail-header";
import { TrendChart } from "@/components/health/trend-chart";
import { StatTile } from "@/components/health/stat-tile";
import { SleepStagesBar } from "@/components/health/sleep-stages-bar";

export const dynamic = "force-dynamic";

function formatDuration(totalSeconds: number): string {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.round((totalSeconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export default async function SleepDetail() {
  const [nights, summary] = await Promise.all([getSleepNights(14), getSummary()]);

  const scorePoints = nights
    .filter((n) => n.sleepScore != null)
    .map((n) => ({ t: n.t, v: n.sleepScore as number }));
  const durationPoints = nights.map((n) => ({ t: n.t, v: Math.round(n.sleepSeconds / 60) }));
  const scoreStats = summarize(scorePoints);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 pb-10 pt-8 sm:max-w-2xl lg:max-w-4xl lg:pt-12">
      <DetailHeader
        icon={Bed}
        color="teal"
        title="Sleep"
        subtitle={`${formatDuration(summary.sleepSeconds ?? 0)} last night · score ${summary.sleepScore ?? "--"}`}
      />

      <div className="rounded-3xl border border-border bg-card p-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Sleep score, last {nights.length} nights
        </p>
        {scorePoints.length > 1 ? (
          <TrendChart points={scorePoints} color="#008c82" timeFormat="day" />
        ) : (
          <p className="py-16 text-center text-sm text-muted-foreground">
            Not enough nights logged yet.
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 rounded-3xl border border-border bg-card p-5">
        <StatTile label="Lowest score" value={scoreStats.min ?? "--"} />
        <StatTile label="Average score" value={scoreStats.avg ?? "--"} />
        <StatTile label="Best score" value={scoreStats.max ?? "--"} />
      </div>

      {durationPoints.length > 1 && (
        <div className="rounded-3xl border border-border bg-card p-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Duration, last {nights.length} nights (minutes)
          </p>
          <TrendChart points={durationPoints} color="#008c82" height={140} timeFormat="day" />
        </div>
      )}

      <div className="rounded-3xl border border-border bg-card p-5">
        <span className="mb-2 block text-[11px] uppercase tracking-wider text-muted-foreground">
          Last night&rsquo;s stages
        </span>
        <SleepStagesBar
          deep={summary.deepSleepSeconds}
          light={summary.lightSleepSeconds}
          rem={summary.remSleepSeconds}
          awake={summary.awakeSleepSeconds}
        />
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-3xl border border-border bg-card p-5">
          <StatTile label="Blood oxygen" value={summary.sleepSpO2 ?? "--"} unit="%" />
        </div>
        <div className="rounded-3xl border border-border bg-card p-5">
          <StatTile label="Breathing rate" value={summary.breathingRate ?? "--"} unit="brpm" />
        </div>
      </div>
    </main>
  );
}
