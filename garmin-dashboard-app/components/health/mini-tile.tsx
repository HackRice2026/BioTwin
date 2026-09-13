import Link from "next/link";
import type { LucideIcon } from "lucide-react";
import { IconBadge, type MetricColor } from "./icon-badge";

/** Compact icon + label + value tile for metrics that are a single daily
 * snapshot rather than a time series (distance, floors, weight, ...) --
 * dense, no wasted space, several per row instead of one hero card each. */
export function MiniTile({
  icon,
  color,
  label,
  value,
  unit,
  href,
}: {
  icon: LucideIcon;
  color: MetricColor;
  label: string;
  value: string | number;
  unit?: string;
  href?: string;
}) {
  const content = (
    <>
      <IconBadge icon={icon} color={color} size={30} />
      <div className="min-w-0">
        <p className="truncate text-[10px] uppercase tracking-wider text-muted-foreground">
          {label}
        </p>
        <p className="truncate text-sm font-semibold text-foreground">
          {value}
          {unit && <span className="ml-0.5 text-[11px] font-medium text-muted-foreground">{unit}</span>}
        </p>
      </div>
    </>
  );

  const className =
    "flex items-center gap-2.5 rounded-2xl border border-border bg-card p-3";

  if (href) {
    return (
      <Link href={href} className={className + " hover:border-foreground/15"}>
        {content}
      </Link>
    );
  }
  return <div className={className}>{content}</div>;
}
