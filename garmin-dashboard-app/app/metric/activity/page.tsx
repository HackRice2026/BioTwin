import { Footprints } from "lucide-react";
import {
  getDistanceHistory,
  getStepsHistory,
  getSummary,
  type Range,
} from "@/lib/health-data";
import { summarize } from "@/lib/stats";
import { DetailHeader } from "@/components/health/detail-header";
import { RangeTabs } from "@/components/health/range-tabs";
import { TrendChart } from "@/components/health/trend-chart";
import { StatTile } from "@/components/health/stat-tile";

export const dynamic = "force-dynamic";

export default async function ActivityDetail({
  searchParams,
}: {
  searchParams: Promise<{ range?: string }>;
}) {
  const range: Range = (await searchParams).range === "week" ? "week" : "day";
  const [stepsPoints, distancePoints, summary] = await Promise.all([
    getStepsHistory(range),
    getDistanceHistory(range),
    getSummary(),
  ]);
  const stepStats = summarize(stepsPoints);
  const timeFormat = range === "day" ? "clock" : "day";

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 pb-10 pt-8 sm:max-w-2xl lg:max-w-4xl lg:pt-12">
      <DetailHeader
        icon={Footprints}
        color="amber"
        title="Activity"
        subtitle={`${summary.steps?.toLocaleString() ?? "--"} steps today`}
      />

      <RangeTabs basePath="/metric/activity" current={range} />

      <div className="rounded-3xl border border-border bg-card p-5">
        <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Steps {range === "day" ? "(last 24h, rolling)" : "(last 7 days)"}
        </p>
        <TrendChart points={stepsPoints} color="#c96a1e" timeFormat={timeFormat} />
      </div>

      <div className="grid grid-cols-3 gap-3 rounded-3xl border border-border bg-card p-5">
        <StatTile label={range === "day" ? "Busiest half-hour" : "Best day"} value={stepStats.max ?? "--"} />
        <StatTile label="Average" value={stepStats.avg ?? "--"} />
        <StatTile label="Total today" value={summary.steps?.toLocaleString() ?? "--"} />
      </div>

      {distancePoints.length > 1 && (
        <div className="rounded-3xl border border-border bg-card p-5">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
            Distance (m)
          </p>
          <TrendChart points={distancePoints} color="#e0a672" height={140} timeFormat={timeFormat} />
        </div>
      )}

      <div className="grid grid-cols-2 gap-3">
        <div className="rounded-3xl border border-border bg-card p-5">
          <StatTile
            label="Distance today"
            value={((summary.distanceMeters ?? 0) / 1000).toFixed(2)}
            unit="km"
          />
        </div>
        <div className="rounded-3xl border border-border bg-card p-5">
          <StatTile label="Floors climbed" value={summary.floorsAscended ?? "--"} />
        </div>
        <div className="rounded-3xl border border-border bg-card p-5">
          <StatTile
            label="Active calories"
            value={summary.calories?.toLocaleString() ?? "--"}
            unit="kcal"
          />
        </div>
      </div>
    </main>
  );
}
