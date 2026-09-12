import type { LucideIcon } from "lucide-react";
import { IconBadge, type MetricColor } from "./icon-badge";
import { StatTile } from "./stat-tile";
import { Sparkline } from "./sparkline";

const LINE_COLOR: Record<MetricColor, string> = {
  coral: "#dd5a49",
  violet: "#9a63de",
  teal: "#008c82",
  amber: "#c96a1e",
};

export function MetricCard({
  icon,
  color,
  title,
  value,
  unit,
  points,
}: {
  icon: LucideIcon;
  color: MetricColor;
  title: string;
  value: string | number;
  unit?: string;
  points?: { t: string; v: number }[];
}) {
  return (
    <div className="flex h-full flex-col gap-3 rounded-3xl border border-border bg-card p-5">
      <div className="flex items-center gap-3">
        <IconBadge icon={icon} color={color} />
        <StatTile label={title} value={value} unit={unit} />
      </div>
      {points && points.length > 1 && (
        <Sparkline points={points} color={LINE_COLOR[color]} height={48} />
      )}
    </div>
  );
}
