import type { LucideIcon } from "lucide-react";
import { cn } from "@/lib/utils";

const FILL_CLASS = {
  coral: "bg-coral-fill text-coral",
  violet: "bg-violet-fill text-violet",
  teal: "bg-teal-fill text-teal",
  amber: "bg-amber-fill text-amber",
} as const;

export type MetricColor = keyof typeof FILL_CLASS;

/** Soft-tinted circular icon container -- one per metric-category card, per designdoc.md */
export function IconBadge({
  icon: Icon,
  color,
  size = 44,
  className,
}: {
  icon: LucideIcon;
  color: MetricColor;
  size?: number;
  className?: string;
}) {
  return (
    <div
      className={cn(
        "flex items-center justify-center rounded-full shrink-0",
        FILL_CLASS[color],
        className,
      )}
      style={{ width: size, height: size }}
    >
      <Icon size={size * 0.5} strokeWidth={2} />
    </div>
  );
}
