import { BatteryMedium } from "lucide-react";
import { getBodyBatteryHistory, getSummary, type Range } from "@/lib/health-data";
import { summarize } from "@/lib/stats";
import { DetailHeader } from "@/components/health/detail-header";
import { RangeTabs } from "@/components/health/range-tabs";
import { TrendChart } from "@/components/health/trend-chart";
import { StatTile } from "@/components/health/stat-tile";

export const dynamic = "force-dynamic";

export default async function BodyBatteryDetail({
  searchParams,
}: {
  searchParams: Promise<{ range?: string }>;
}) {
  const range: Range = (await searchParams).range === "week" ? "week" : "day";
  const [points, summary] = await Promise.all([getBodyBatteryHistory(range), getSummary()]);
  const stats = summarize(points);

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 pb-10 pt-8 sm:max-w-2xl lg:max-w-4xl lg:pt-12">
      <DetailHeader
        icon={BatteryMedium}
        color="violet"
        title="Body Battery"
        subtitle={`Currently ${summary.bodyBattery ?? "--"} / 100`}
      />

      <RangeTabs basePath="/metric/body-battery" current={range} />

      <div className="rounded-3xl border border-border bg-card p-5">
        <TrendChart
          points={points}
          color="#9a63de"
          timeFormat={range === "day" ? "clock" : "day-time"}
        />
      </div>

      <div className="grid grid-cols-3 gap-3 rounded-3xl border border-border bg-card p-5">
        <StatTile label="Lowest" value={stats.min ?? "--"} />
        <StatTile label="Average" value={stats.avg ?? "--"} />
        <StatTile label="Highest" value={stats.max ?? "--"} />
      </div>

      <p className="px-1 text-xs text-muted-foreground">
        A 0&ndash;100 estimate of your reserve energy, drained by stress and
        activity, recharged mainly by sleep.
      </p>
    </main>
  );
}
