import { cn } from "@/lib/utils";

/** micro-label -> hero value -> optional unit, per designdoc.md's stat tile pattern */
export function StatTile({
  label,
  value,
  unit,
  className,
}: {
  label: string;
  value: string | number;
  unit?: string;
  className?: string;
}) {
  return (
    <div className={cn("flex flex-col", className)}>
      <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
        {label}
      </span>
      <span className="mt-0.5 font-semibold text-foreground text-2xl leading-none">
        {value}
        {unit && (
          <span className="ml-1 text-sm font-medium text-muted-foreground">
            {unit}
          </span>
        )}
      </span>
    </div>
  );
}
