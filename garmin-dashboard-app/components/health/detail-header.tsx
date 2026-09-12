import Link from "next/link";
import { ChevronLeft, type LucideIcon } from "lucide-react";
import { IconBadge, type MetricColor } from "./icon-badge";

export function DetailHeader({
  icon,
  color,
  title,
  subtitle,
}: {
  icon: LucideIcon;
  color: MetricColor;
  title: string;
  subtitle?: string;
}) {
  return (
    <header className="flex flex-col gap-4">
      <Link
        href="/"
        className="inline-flex w-fit items-center gap-1 text-sm text-muted-foreground hover:text-foreground"
      >
        <ChevronLeft size={16} />
        Today&rsquo;s health
      </Link>
      <div className="flex items-center gap-3">
        <IconBadge icon={icon} color={color} size={48} />
        <div>
          <h1 className="font-display text-2xl font-medium text-foreground">
            {title}
          </h1>
          {subtitle && <p className="text-sm text-muted-foreground">{subtitle}</p>}
        </div>
      </div>
    </header>
  );
}
