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
import type { MetricPoint, SleepPoint } from "./api";

const grid = "#e9ece6";
const tooltip = {
  background: "#fff",
  border: "1px solid #e1e7de",
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
}: {
  data: MetricPoint[];
  unit: string;
  days?: number;
}) {
  if (!data.length) return <EmptyChart />;
  const rows = data.map((p) => ({ ...p, time: new Date(p.time).getTime() }));
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
          domain={["dataMin", "dataMax"]}
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
          stroke="#397b65"
          fill="#d9e9df"
          fillOpacity={0.55}
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
    <ResponsiveContainer width="100%" height="100%">
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
          stroke="#224f3b"
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
          fill="#295842"
          name="Deep · min"
        />
        <Bar
          dataKey="light_minutes"
          stackId="a"
          fill="#a6c5b1"
          name="Light · min"
        />
        <Bar
          dataKey="rem_minutes"
          stackId="a"
          fill="#c5dfbd"
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
            fillOpacity={0.65}
          />
        ))}
        <Tooltip contentStyle={tooltip} />
        <Line
          dataKey="score"
          stroke="#2e6750"
          strokeWidth={2.5}
          dot={{ r: 3 }}
          isAnimationActive={false}
          name="Readiness"
        />
      </LineChart>
    </ResponsiveContainer>
  );
}
