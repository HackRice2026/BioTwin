import Link from "next/link";
import { ChevronRight, type LucideIcon } from "lucide-react";
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
  href,
}: {
  icon: LucideIcon;
  color: MetricColor;
  title: string;
  value: string | number;
  unit?: string;
  points?: { t: string; v: number }[];
  /** When set, the whole card links to a detail page -- the "hint to dive
   * into more" pattern from designdoc.md's information hierarchy. */
  href?: string;
}) {
  const body = (
    <div className="flex h-full flex-col gap-3 rounded-3xl border border-border bg-card p-5 transition-colors">
      <div className="flex items-center gap-3">
        <IconBadge icon={icon} color={color} />
        <div className="flex flex-1 items-center justify-between gap-2">
          <StatTile label={title} value={value} unit={unit} />
          {href && (
            <ChevronRight
              size={18}
              className="mt-4 shrink-0 text-muted-foreground"
            />
          )}
        </div>
      </div>
      {points && points.length > 1 && (
        <Sparkline points={points} color={LINE_COLOR[color]} height={48} />
      )}
    </div>
  );

  if (href) {
    return (
      <Link href={href} className="block h-full hover:opacity-90">
        {body}
      </Link>
    );
  }
  return body;
}
