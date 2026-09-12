const STAGES = [
  { key: "deep", label: "Deep", color: "#005e57" },
  { key: "rem", label: "REM", color: "#008c82" },
  { key: "light", label: "Light", color: "#5cb8b1" },
  { key: "awake", label: "Awake", color: "#c7e6e3" },
] as const;

function formatMinutes(seconds: number): string {
  const m = Math.round(seconds / 60);
  const h = Math.floor(m / 60);
  const rem = m % 60;
  return h > 0 ? `${h}h ${rem}m` : `${rem}m`;
}

/**
 * Sub-segments of ONE metric (sleep stages) use a sequential single-hue
 * ramp (light -> dark teal), not the four categorical family colors --
 * those are reserved for distinguishing different metric families, per
 * designdoc.md.
 */
export function SleepStagesBar({
  deep,
  light,
  rem,
  awake,
}: {
  deep: number | null;
  light: number | null;
  rem: number | null;
  awake: number | null;
}) {
  const values = { deep: deep ?? 0, light: light ?? 0, rem: rem ?? 0, awake: awake ?? 0 };
  const total = values.deep + values.light + values.rem + values.awake;
  if (total === 0) {
    return <p className="text-sm text-muted-foreground">No sleep stage data yet.</p>;
  }

  return (
    <div>
      <div className="flex h-3 w-full overflow-hidden rounded-full gap-[2px]">
        {STAGES.map((stage) => {
          const seconds = values[stage.key as keyof typeof values];
          const pct = (seconds / total) * 100;
          if (pct <= 0) return null;
          return (
            <div
              key={stage.key}
              style={{ width: `${pct}%`, backgroundColor: stage.color }}
              title={`${stage.label}: ${formatMinutes(seconds)}`}
            />
          );
        })}
      </div>
      <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
        {STAGES.map((stage) => {
          const seconds = values[stage.key as keyof typeof values];
          return (
            <div key={stage.key} className="flex items-center gap-1.5 text-xs">
              <span
                className="h-2 w-2 rounded-full"
                style={{ backgroundColor: stage.color }}
              />
              <span className="text-muted-foreground">{stage.label}</span>
              <span className="font-medium text-foreground">
                {formatMinutes(seconds)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
