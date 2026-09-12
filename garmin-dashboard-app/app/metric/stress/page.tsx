import { Waves } from "lucide-react";
import { getStressHistory, getSummary, type Range } from "@/lib/health-data";
import { summarize } from "@/lib/stats";
import { DetailHeader } from "@/components/health/detail-header";
import { RangeTabs } from "@/components/health/range-tabs";
import { TrendChart } from "@/components/health/trend-chart";
import { StatTile } from "@/components/health/stat-tile";

export const dynamic = "force-dynamic";

function stressLabel(level: number | null): string {
  if (level == null) return "--";
  if (level < 25) return "Resting";
  if (level < 50) return "Low";
  if (level < 75) return "Medium";
  return "High";
}

export default async function StressDetail({
  searchParams,
}: {
  searchParams: Promise<{ range?: string }>;
}) {
  const range: Range = (await searchParams).range === "week" ? "week" : "day";
  const [points, summary] = await Promise.all([getStressHistory(range), getSummary()]);
  const stats = summarize(points);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 pb-10 pt-8 sm:max-w-2xl lg:max-w-4xl lg:pt-12">
      <DetailHeader
        icon={Waves}
        color="violet"
        title="Stress"
        subtitle={`Currently ${stressLabel(summary.stressLevel)}${
          summary.stressLevel != null && summary.stressLevel >= 0 ? ` (${summary.stressLevel})` : ""
        }`}
        backRange={range}
      />

      <RangeTabs basePath="/metric/stress" current={range} />

      <div className="rounded-3xl border border-border bg-card p-5">
        {points.length > 1 ? (
          <TrendChart
            points={points}
            color="#9a63de"
            timeFormat={range === "day" ? "clock" : "day-time"}
          />
        ) : (
          <p className="py-16 text-center text-sm text-muted-foreground">
            Not enough stress data in this range yet.
          </p>
        )}
      </div>

      <div className="grid grid-cols-3 gap-3 rounded-3xl border border-border bg-card p-5">
        <StatTile label="Low" value={stats.min ?? "--"} />
        <StatTile label="Average" value={stats.avg ?? "--"} />
        <StatTile label="High" value={stats.max ?? "--"} />
      </div>

      <p className="px-1 text-xs text-muted-foreground">
        Scored 0&ndash;100 from heart-rate variability: 0&ndash;25 resting,
        25&ndash;50 low, 50&ndash;75 medium, 75+ high.
      </p>
    </main>
  );
}
