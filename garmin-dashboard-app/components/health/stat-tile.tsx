import { cn } from "@/lib/utils";

/** micro-label -> hero value -> optional unit, per designdoc.md's stat tile pattern.
 * `size="sm"` is for dense grids (a chart's stat row, an at-a-glance tile) where a
 * full 2xl hero figure would blow out the layout -- same anatomy, smaller scale. */
export function StatTile({
  label,
  value,
  unit,
  size = "lg",
  className,
}: {
  label: string;
  value: string | number;
  unit?: string;
  size?: "sm" | "lg";
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col", className)}>
      <span
        className={cn(
          "uppercase tracking-wider text-muted-foreground",
          size === "sm" ? "text-[10px]" : "text-[11px]",
        )}
      >
        {label}
      </span>
      <span
        className={cn(
          "font-semibold text-foreground leading-none",
          size === "sm" ? "mt-1 text-base" : "mt-0.5 text-2xl",
        )}
      >
        {value}
        {unit && (
          <span
            className={cn(
              "font-medium text-muted-foreground",
              size === "sm" ? "ml-0.5 text-[11px]" : "ml-1 text-sm",
            )}
          >
            {unit}
          </span>
        )}
      </span>
    </div>
  );
}
