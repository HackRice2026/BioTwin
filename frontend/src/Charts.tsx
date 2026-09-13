import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import type {
  RecoveryPrediction,
  Readiness,
  SimulationOverlay,
  DayOutlook,
} from "./contracts";
import { humanize, type MetricPoint, type SleepPoint } from "./api";

const grid = "#ffffff0b";
const tooltip = {
  background: "#202829",
  color: "#f5f8f7",
  border: "1px solid #ffffff20",
  borderRadius: 12,
  fontSize: 12,
  boxShadow: "0 8px 24px #153b3210",
};
const tick = { fontSize: 10, fill: "#839087" };

export function OutlookChart({ outlook }: { outlook: DayOutlook | null }) {
  if (!outlook?.curve.length)
    return (
      <EmptyChart
        message={
          outlook?.assumptions ?? "Gathering the signals for your day outlook."
        }
      />
    );
  return (
    <ResponsiveContainer width="100%" height={200}>
      <LineChart
        data={outlook.curve.map((p) => ({
          time: new Date(p.time).getTime(),
          score: p.value,
        }))}
        margin={{ left: -20, top: 15, right: 10 }}
      >
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis
          dataKey="time"
          type="number"
          domain={["dataMin", "dataMax"]}
          tick={tick}
          tickFormatter={clock}
          axisLine={false}
          tickLine={false}
        />
        <YAxis
          tick={tick}
          domain={[0, 100]}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={tooltip}
          labelFormatter={(n) => clock(Number(n))}
        />
        <Line
          dataKey="score"
          stroke="#a18e64"
          strokeWidth={2}
          strokeDasharray="6 4"
          dot={false}
          isAnimationActive={false}
          name="Experimental readiness projection"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
const date = (n: number | string) =>
  new Date(n).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const clock = (n: number | string) =>
  new Date(n).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
  });

export function ProvenanceChip({ source }: { source?: string }) {
  const label = !source
    ? "NO DATA"
    : source === "synthetic"
      ? "SYNTHETIC"
      : source.includes("replay")
        ? "RECORDED"
        : source.includes("backfill")
          ? "BACKFILL"
          : source === "simulated"
            ? "SIMULATED"
            : "MEASURED";
  return (
    <span
      className={`provenance ${label === "SYNTHETIC" || label === "SIMULATED" ? "synthetic" : ""}`}
    >
      {label}
    </span>
  );
}
export function EmptyChart({
  message = "Connect your wearable to start building this view.",
}: {
  message?: string;
}) {
  return (
    <div className="empty-chart">
      <span className="empty-wave">⌁</span>
      <p>{message}</p>
    </div>
  );
}
export function Sparkline({
  data,
  color = "#477c69",
}: {
  data: MetricPoint[];
  color?: string;
}) {
  if (data.length < 2) return <div className="empty-spark" />;
  return (
    <ResponsiveContainer width="100%" height={38}>
      <AreaChart data={data.slice(-25)}>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.7}
          fill={color}
          fillOpacity={0.06}
          isAnimationActive={false}
          dot={false}
        />
        <YAxis hide domain={["dataMin - 2", "dataMax + 2"]} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
export function SignalChart({
  data,
  unit,
  days = 7,
  color = "#7bdfa7",
}: {
  data: MetricPoint[];
  unit: string;
  days?: number;
  color?: string;
}) {
  if (!data.length) return <EmptyChart />;
  const rows = data.map((p) => ({ ...p, time: new Date(p.time).getTime() }));
  const rangeEnd = Date.now();
  const rangeStart = rangeEnd - days * 24 * 60 * 60 * 1000;
  return (
    <ResponsiveContainer width="100%" height={220}>
      <AreaChart
        data={rows}
        margin={{ top: 12, right: 8, bottom: 0, left: -20 }}
      >
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis
          dataKey="time"
          type="number"
          domain={[rangeStart, rangeEnd]}
          tick={tick}
          tickFormatter={days === 1 ? clock : date}
          tickLine={false}
          axisLine={false}
        />
        <YAxis
          tick={tick}
          tickLine={false}
          axisLine={false}
          domain={["auto", "auto"]}
        />
        <Tooltip
          contentStyle={tooltip}
          labelFormatter={(n) => new Date(Number(n)).toLocaleString()}
          formatter={(v) => [`${v} ${unit}`, "Recorded"]}
        />
        <Area
          dataKey="value"
          stroke={color}
          fill={color}
          fillOpacity={0.08}
          strokeWidth={2}
          dot={false}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  );
}
export function RecoveryChart({
  prediction,
  simulation,
}: {
  prediction?: RecoveryPrediction | null;
  simulation?: SimulationOverlay | null;
}) {
  if (!prediction && !simulation)
    return (
      <EmptyChart message="Recovery predictions appear after enough recorded recovery sessions. Import a few workouts to calibrate your twin." />
    );
  const points = simulation?.curve ?? prediction!.curve;
  const rows = new Map<
    number,
    {
      time: number;
      predicted?: number;
      observed?: number;
      band?: [number, number];
    }
  >();
  for (const p of points) {
    const time = new Date(p.time).getTime();
    rows.set(time, {
      time,
      predicted: p.value,
      ...(p.lower != null && p.upper != null
        ? { band: [p.lower, p.upper] as [number, number] }
        : {}),
    });
  }
  if (!simulation)
    for (const p of prediction?.observed ?? []) {
      const time = new Date(p.time).getTime();
      rows.set(time, { ...rows.get(time), time, observed: p.value });
    }
  return (
    <ResponsiveContainer width="100%" height={190}>
      <ComposedChart
        data={[...rows.values()].sort((a, b) => a.time - b.time)}
        margin={{ top: 12, right: 5, left: -20, bottom: 0 }}
      >
        <CartesianGrid vertical={false} stroke={grid} />
        <XAxis
          dataKey="time"
          type="number"
          domain={["dataMin", "dataMax"]}
          tickFormatter={clock}
          tick={tick}
          axisLine={false}
          tickLine={false}
          minTickGap={35}
        />
        <YAxis
          tick={tick}
          domain={["auto", "auto"]}
          axisLine={false}
          tickLine={false}
        />
        <Tooltip
          contentStyle={tooltip}
          labelFormatter={(v) => clock(Number(v))}
        />
        <Area
          dataKey="band"
          fill="#5f997b"
          fillOpacity={0.1}
          stroke="none"
          connectNulls
          isAnimationActive={false}
          name="±2 held-out RMSE"
        />
        <Line
          dataKey="predicted"
          stroke={simulation ? "#a1895f" : "#6c907d"}
          strokeWidth={2}
          strokeDasharray="5 5"
          dot={false}
          connectNulls
          isAnimationActive={false}
          name={simulation ? "SIMULATED" : "Predicted"}
        />
        <Line
          dataKey="observed"
          stroke="#7bdfa7"
          strokeWidth={2.5}
          dot={false}
          connectNulls
          isAnimationActive={false}
          name="Observed"
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
export function SleepChart({ data }: { data: SleepPoint[] }) {
  if (!data.length) return <EmptyChart />;
  const rows = data.slice(-7).map((p) => ({ date: date(p.time), ...p.value }));
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={rows} barSize={28} margin={{ left: -20, top: 10 }}>
        <CartesianGrid vertical={false} stroke={grid} />
        <XAxis dataKey="date" tick={tick} axisLine={false} tickLine={false} />
        <YAxis tick={tick} axisLine={false} tickLine={false} />
        <Tooltip contentStyle={tooltip} />
        <Bar
          dataKey="deep_minutes"
          stackId="a"
          fill="#5089d6"
          name="Deep · min"
        />
        <Bar
          dataKey="light_minutes"
          stackId="a"
          fill="#9cc9f6"
          name="Light · min"
        />
        <Bar
          dataKey="rem_minutes"
          stackId="a"
          fill="#79d8b0"
          name="REM · min"
        />
        <Bar
          dataKey="awake_minutes"
          stackId="a"
          fill="#e5ce9c"
          name="Awake · min"
          radius={[4, 4, 0, 0]}
        />
      </BarChart>
    </ResponsiveContainer>
  );
}
export function ReadinessChart({
  data,
  cuts,
}: {
  data: Readiness[];
  cuts: number[];
}) {
  if (!data.length) return <EmptyChart />;
  const boundaries = [0, ...cuts, 100],
    colors = ["#fae7df", "#f6e8d4", "#f1edd6", "#e9efde", "#dcebdc", "#cee5d2"];
  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart
        data={data.map((p) => ({ ...p, date: date(p.computed_at) }))}
        margin={{ top: 10, left: -20, right: 5 }}
      >
        <CartesianGrid stroke={grid} vertical={false} />
        <XAxis dataKey="date" tick={tick} axisLine={false} tickLine={false} />
        <YAxis
          tick={tick}
          domain={[0, 100]}
          axisLine={false}
          tickLine={false}
        />
        {colors.map((color, i) => (
          <ReferenceArea
            key={i}
            y1={boundaries[i]}
            y2={boundaries[i + 1]}
            fill={color}
            fillOpacity={0.06}
          />
        ))}
        <Tooltip contentStyle={tooltip} />
        <Line
          dataKey="score"
          stroke="#7bdfa7"
          strokeWidth={2.5}
          dot={{ r: 3 }}
          isAnimationActive={false}
          name="Readiness"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}

export function TrajectoryChart({
  measured,
  points,
  referenceLabel = "now",
}: {
  measured: { minutes_ago: number; value: number }[];
  points: {
    horizon_minutes: number;
    value: number;
    validation_mae: number;
    method: string;
    beats_baseline: boolean;
  }[];
  referenceLabel?: string;
}) {
  if (!measured.length && !points.length)
    return <EmptyChart message="Body Battery readings appear once your watch syncs." />;
  // One x axis in hours, negative behind and positive ahead, so the measured
  // past and the prediction share a scale and meet at zero. The band carries
  // each point's own validation error, which is why it widens rightward.
  const rows = [
    ...measured.map((m) => ({
      hours: -m.minutes_ago / 60,
      observed: m.value,
      ...(m === measured[measured.length - 1]
        ? { predicted: m.value, low: m.value, high: m.value }
        : {}),
    })),
    ...points.map((p) => ({
      hours: p.horizon_minutes / 60,
      predicted: p.value,
      low: Math.max(0, p.value - p.validation_mae),
      high: Math.min(100, p.value + p.validation_mae),
    })),
  ];
  const first = rows.length ? rows[0].hours : -1;
  return (
    <ResponsiveContainer width="100%" height="100%">
      <ComposedChart data={rows} margin={{ top: 12, right: 8, left: -22, bottom: 0 }}>
        <CartesianGrid vertical={false} stroke={grid} />
        <XAxis
          dataKey="hours"
          type="number"
          domain={[Math.floor(first), 6]}
          ticks={[Math.floor(first), -6, -3, 0, 1, 3, 6].filter(
            (h, i, a) => h >= Math.floor(first) && a.indexOf(h) === i,
          )}
          tickFormatter={(h: number) => (h === 0 ? referenceLabel : h < 0 ? `${h}h` : `+${h}h`)}
          tick={tick}
          axisLine={false}
          tickLine={false}
        />
        <YAxis tick={tick} domain={[0, 100]} axisLine={false} tickLine={false} />
        <Tooltip
          contentStyle={tooltip}
          labelFormatter={(h) =>
            Number(h) === 0
              ? humanize(referenceLabel)
              : Number(h) < 0
                ? `${Math.abs(Number(h)).toFixed(1)}h ago`
                : `In ${h}h`
          }
          formatter={(v, name) => [
            `${v}%`,
            name === "observed"
              ? "Measured"
              : name === "predicted"
                ? "Predicted"
                : name === "high"
                  ? "Upper"
                  : "Lower",
          ]}
        />
        <Area dataKey="high" stroke="none" fill="var(--green)" fillOpacity={0.14} isAnimationActive={false} />
        <Area dataKey="low" stroke="none" fill="#17221e" fillOpacity={1} isAnimationActive={false} />
        <Line
          dataKey="observed"
          stroke="var(--green)"
          strokeWidth={2}
          dot={false}
          connectNulls
          isAnimationActive={false}
        />
        <Line
          dataKey="predicted"
          stroke="var(--green)"
          strokeWidth={2}
          strokeDasharray="5 4"
          dot={{ r: 3, fill: "var(--green)", stroke: "none" }}
          connectNulls
          isAnimationActive={false}
        />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
