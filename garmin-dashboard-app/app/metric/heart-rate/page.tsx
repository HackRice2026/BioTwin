import { HeartPulse } from "lucide-react";
import { getHeartRateHistory, getSummary, type Range } from "@/lib/health-data";
import { summarize } from "@/lib/stats";
import { DetailHeader } from "@/components/health/detail-header";
import { RangeTabs } from "@/components/health/range-tabs";
import { TrendChart } from "@/components/health/trend-chart";
import { StatTile } from "@/components/health/stat-tile";

export const dynamic = "force-dynamic";

export default async function HeartRateDetail({
  searchParams,
}: {
  searchParams: Promise<{ range?: string }>;
}) {
  const range: Range = (await searchParams).range === "week" ? "week" : "day";
  const [points, summary] = await Promise.all([getHeartRateHistory(range), getSummary()]);
  const stats = summarize(points);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 pb-10 pt-8 sm:max-w-2xl lg:max-w-4xl lg:pt-12">
      <DetailHeader
        icon={HeartPulse}
        color="coral"
        title="Heart Rate"
        subtitle={`Currently ${summary.latestHr ?? "--"} bpm`}
        backRange={range}
      />

      <RangeTabs basePath="/metric/heart-rate" current={range} />

      <div className="rounded-3xl border border-border bg-card p-5">
        <TrendChart
          points={points}
          color="#dd5a49"
          unit=" bpm"
          timeFormat={range === "day" ? "clock" : "day-time"}
        />
      </div>

      <div className="grid grid-cols-3 gap-3 rounded-3xl border border-border bg-card p-5 sm:grid-cols-5">
        <StatTile label="Min" value={stats.min ?? "--"} unit="bpm" />
        <StatTile label="Avg" value={stats.avg ?? "--"} unit="bpm" />
        <StatTile label="Max" value={stats.max ?? "--"} unit="bpm" />
        <StatTile label="Resting" value={summary.restingHr ?? "--"} unit="bpm" />
        <StatTile
          label="Today's range"
          value={
            summary.minHr != null && summary.maxHr != null
              ? `${summary.minHr}–${summary.maxHr}`
              : "--"
          }
        />
      </div>
    </main>
  );
}
