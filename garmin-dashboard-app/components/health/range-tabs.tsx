import Link from "next/link";
import { cn } from "@/lib/utils";
import type { Range } from "@/lib/health-data";

const OPTIONS: { key: Range; label: string }[] = [
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
];

/** Pill segmented control, per designdoc.md -- rounded-full track, active
 * segment gets primary-ink background + cream text. Plain links (not a
 * client component) so range switching is a real navigation, no client
 * data-fetching machinery needed. */
export function RangeTabs({ basePath, current }: { basePath: string; current: Range }) {
  return (
    <div className="inline-flex rounded-full bg-muted p-1">
      {OPTIONS.map((o) => (
        <Link
          key={o.key}
          href={`${basePath}?range=${o.key}`}
          className={cn(
            "rounded-full px-4 py-1.5 text-sm font-medium transition-colors",
            current === o.key
              ? "bg-foreground text-background"
              : "text-muted-foreground hover:text-foreground",
          )}
        >
          {o.label}
        </Link>
      ))}
    </div>
  );
}
