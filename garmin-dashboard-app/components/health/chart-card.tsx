import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { IconBadge, type MetricColor } from "./icon-badge";
import { StatTile } from "./stat-tile";
import { TrendChart } from "./trend-chart";
import { summarize } from "@/lib/stats";
import type { SeriesPoint } from "@/lib/health-data";

const LINE_COLOR: Record<MetricColor, string> = {
  coral: "#dd5a49",
  violet: "#9a63de",
  teal: "#008c82",
  amber: "#c96a1e",
};

/**
 * A real chart, inline, with its stats -- not a sparkline behind a tap.
 * This is the density fix: the pattern should be readable on the home
 * grid itself, the detail page (href) is for going deeper, not for
 * finding out there's a pattern at all.
 */
export function ChartCard({
  icon,
  color,
  title,
  current,
  unit,
  points,
  href,
  timeFormat = "clock",
}: {
  icon: LucideIcon;
  color: MetricColor;
  title: string;
  current: string | number;
  unit?: string;
  points: SeriesPoint[];
  href: string;
  timeFormat?: "clock" | "day-time" | "day";
}) {
  const stats = summarize(points);

  return (
    <Link
      href={href}
      className="flex flex-col gap-3 rounded-2xl border border-border bg-card p-4 hover:border-foreground/15"
    >
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <IconBadge icon={icon} color={color} size={34} />
          <div>
            <p className="text-[11px] uppercase tracking-wider text-muted-foreground">
              {title}
            </p>
            <p className="text-lg font-semibold leading-none text-foreground">
              {current}
              {unit && (
                <span className="ml-1 text-xs font-medium text-muted-foreground">
                  {unit}
                </span>
              )}
            </p>
          </div>
        </div>
        <div className="hidden gap-4 sm:flex">
          <StatTile size="sm" label="Min" value={stats.min ?? "--"} />
          <StatTile size="sm" label="Avg" value={stats.avg ?? "--"} />
          <StatTile size="sm" label="Max" value={stats.max ?? "--"} />
        </div>
      </div>

      {points.length > 1 ? (
        <TrendChart
          points={points}
          color={LINE_COLOR[color]}
          height={104}
          timeFormat={timeFormat}
        />
      ) : (
        <div className="flex h-[104px] items-center justify-center rounded-xl bg-muted text-xs text-muted-foreground">
          Not enough data yet
        </div>
      )}

      <div className="flex justify-between gap-4 sm:hidden">
        <StatTile size="sm" label="Min" value={stats.min ?? "--"} />
        <StatTile size="sm" label="Avg" value={stats.avg ?? "--"} />
        <StatTile size="sm" label="Max" value={stats.max ?? "--"} />
      </div>
    </Link>
  );
}
