import type { ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  Battery,
  CalendarDays,
  Check,
  Flame,
  Footprints,
  Heart,
  Leaf,
  LoaderCircle,
  Moon,
  RefreshCw,
  Wind,
} from "lucide-react";
import { humanize, value, post } from "./api";
import type { Dashboard } from "./useDashboard";
import {
  OutlookChart,
  ReadinessChart,
  RecoveryChart,
  SignalChart,
  SleepChart,
  Sparkline,
} from "./Charts";
import type { Topic } from "./topics";
export const signalDefinitions = [
  {
    field: "heart_rate_bpm",
    name: "Heart rate",
    unit: "bpm",
    icon: Heart,
    tone: "red",
  },
  { field: "sleep", name: "Sleep", unit: "hrs", icon: Moon, tone: "blue" },
  {
    field: "active_kcal",
    name: "Calories burned",
    unit: "active kcal",
    icon: Flame,
    tone: "amber",
  },
  {
    field: "steps",
    name: "Steps",
    unit: "steps",
    icon: Footprints,
    tone: "green",
  },
  {
    field: "hrv_rmssd_ms",
    name: "Heart-rate variability",
    unit: "ms",
    icon: Activity,
    tone: "blue",
  },
  {
    field: "resting_hr_bpm",
    name: "Resting heart rate",
    unit: "bpm",
    icon: Heart,
    tone: "red",
  },
  {
    field: "respiration_brpm",
    name: "Respiration",
    unit: "br/min",
    icon: Wind,
    tone: "blue",
  },
  {
    field: "spo2_pct",
    name: "Blood oxygen",
    unit: "%",
    icon: Activity,
    tone: "blue",
  },
  {
    field: "stress_level",
    name: "Stress",
    unit: "/100",
    icon: Activity,
    tone: "amber",
  },
  {
    field: "body_battery_pct",
    name: "Garmin Body Battery",
    unit: "%",
    icon: Battery,
    tone: "green",
  },
  {
    field: "distance_meters",
    name: "Distance",
    unit: "m",
    icon: Footprints,
    tone: "green",
  },
  {
    field: "floors_ascended",
    name: "Floors climbed",
    unit: "floors",
    icon: Footprints,
    tone: "green",
  },
  {
    field: "max_hr_bpm",
    name: "Highest heart rate",
    unit: "bpm",
    icon: Heart,
    tone: "red",
  },
  {
    field: "min_hr_bpm",
    name: "Lowest heart rate",
    unit: "bpm",
    icon: Heart,
    tone: "red",
  },
];
export const topicSignal: Partial<Record<Topic, string>> = {
  heart: "heart_rate_bpm",
  sleep: "sleep",
  calories: "active_kcal",
  steps: "steps",
};
export function Panel({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`glass ${className}`}>{children}</section>;
}
export function PanelTitle({
  title,
  note,
  children,
}: {
  title: string;
  note?: string;
  children?: ReactNode;
}) {
  return (
    <div className="panel-title">
      <div>
        <h2>{title}</h2>
        {note && <p>{note}</p>}
      </div>
      {children}
    </div>
  );
}
export function Range({ data }: { data: Dashboard }) {
  return (
    <div className="segmented" aria-label="Chart range">
      {[1, 7, 28].map((days) => (
        <button
          key={days}
          aria-pressed={data.days === days}
          className={data.days === days ? "selected" : ""}
          onClick={() => data.setDays(days)}
        >
          {days === 1 ? "Day" : days === 7 ? "Week" : "28 days"}
        </button>
      ))}
    </div>
  );
}
export function Metric({
  field,
  data,
  onClick,
}: {
  field: string;
  data: Dashboard;
  onClick: () => void;
}) {
  const def = signalDefinitions.find((s) => s.field === field)!;
  const latest = data.state?.latest;
  const n =
    field === "sleep"
      ? latest?.sleep?.total_minutes == null
        ? null
        : latest.sleep.total_minutes / 60
      : (latest?.[field as keyof typeof latest] as number | null);
  const rows =
    field === "sleep"
      ? data.sleep.map((s) => ({
          time: s.time,
          value: s.value.total_minutes,
          provenance: s.provenance,
          confidence: 1,
        }))
      : data.series(field);
  return (
    <button
      className={`metric glass ${def.tone}`}
      onClick={onClick}
      aria-label={`Explore ${def.name}`}
    >
      <div className="metric-label">
        <def.icon size={17} />
        <span>{def.name}</span>
        <ArrowUpRight size={14} />
      </div>
      <div className="metric-number">
        {value(n, field === "sleep" ? 1 : 0)}
        <small>{def.unit}</small>
      </div>
      <div className="metric-trend">
        <span>
          {n == null
            ? "Awaiting a reading"
            : field === "sleep"
              ? "Latest night"
              : "Latest recorded"}
        </span>
        <div>
          <Sparkline data={rows} color={`var(--${def.tone})`} />
        </div>
      </div>
    </button>
  );
}
export function SignalDetail({
  field,
  data,
}: {
  field: string;
  data: Dashboard;
}) {
  const def = signalDefinitions.find((s) => s.field === field)!;
  const rows = data.series(field);
  const q = data.state?.quality?.[field];
  const latest = data.state?.latest;
  const extras: Record<string, [string, string][]> = {
    steps: [
      ["moderate_intensity_min", "Moderate · min"],
      ["vigorous_intensity_min", "Vigorous · min"],
    ],
    stress_level: [
      ["stress_high_min", "High · min"],
      ["stress_medium_min", "Medium · min"],
      ["stress_low_min", "Low · min"],
    ],
    body_battery_pct: [
      ["body_battery_at_wake", "At wake"],
      ["body_battery_charged", "Charged"],
      ["body_battery_drained", "Drained"],
    ],
  };
  return (
    <div className={`signal-detail ${def.tone}`}>
      <div className="signal-heading">
        <div className="signal-icon">
          <def.icon size={21} />
        </div>
        <div>
          <h2>{def.name}</h2>
          <p>
            {q
              ? `Recorded ${new Date(q.event_time).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}`
              : "No measurement yet"}
          </p>
        </div>
        <Range data={data} />
      </div>
      {field === "sleep" ? (
        <SleepChart data={data.sleep} />
      ) : (
        <SignalChart
          data={rows}
          unit={def.unit}
          days={data.days}
          color={`var(--${def.tone})`}
        />
      )}
      {field === "sleep" ? (
        <div className="chart-key">
          <span className="blue">● Deep</span>
          <span>● Light</span>
          <span className="green">● REM</span>
          <span className="amber">● Awake</span>
          <small>minutes</small>
        </div>
      ) : (
        <div className="signal-stats">
          {[
            ["Latest", rows.at(-1)?.value],
            ["Low", rows.length ? Math.min(...rows.map((r) => r.value)) : null],
            [
              "High",
              rows.length ? Math.max(...rows.map((r) => r.value)) : null,
            ],
          ].map(([label, n]) => (
            <div key={String(label)}>
              <small>{label}</small>
              <b>
                {value(n as number | null, 1)} <em>{def.unit}</em>
              </b>
            </div>
          ))}
        </div>
      )}
      {q?.contested && (
        <p className="notice">
          Sources differ:{" "}
          {(q.alternatives ?? [])
            .map((a) => `${humanize(String(a.source))}: ${a.value}`)
            .join(" · ")}
        </p>
      )}
      {extras[field] && (
        <details className="disclosure">
          <summary>View breakdown</summary>
          <div className="signal-stats">
            {extras[field].map(([key, label]) => (
              <div key={key}>
                <small>{label}</small>
                <b>
                  {value(latest?.[key as keyof typeof latest] as number | null)}
                </b>
              </div>
            ))}
          </div>
        </details>
      )}
    </div>
  );
}
export function ReadinessPanel({ data }: { data: Dashboard }) {
  const r = data.state!.readiness,
    score = r.score;
  return (
    <Panel className="readiness-panel">
      <PanelTitle title="Ready for today" note="Your personal readiness">
        <Leaf size={19} className="green" />
      </PanelTitle>
      <div className="readiness-body">
        <div
          className="readiness-ring"
          style={{
            background: `conic-gradient(var(--green) ${(score ?? 0) * 3.6}deg, #ffffff0a 0deg)`,
          }}
        >
          <div>
            <strong>{value(score)}</strong>
            <small>READINESS</small>
          </div>
        </div>
        <div>
          <span className="pill green">
            {score == null ? "Getting to know you" : humanize(r.state)}
          </span>
          <h3>
            {score == null
              ? "Your story starts here."
              : score >= 65
                ? "A little more in the tank."
                : score >= 45
                  ? "Find your own rhythm."
                  : "Make room to recharge."}
          </h3>
          <p>
            Sleep, heart-rate variability and rest, relative to your pattern.
          </p>
        </div>
      </div>
      <div className="confidence-row">
        <span>Estimate confidence</span>
        <b>{value(r.confidence * 100)}%</b>
      </div>
      <div className="meter">
        <i style={{ width: `${r.confidence * 100}%` }} />
      </div>
    </Panel>
  );
}
export function RecoveryPanel({ data }: { data: Dashboard }) {
  return (
    <Panel>
      <PanelTitle
        title="Recovery in motion"
        note="Heart rate after activity · bpm"
      >
        <Activity size={18} className="green" />
      </PanelTitle>
      <RecoveryChart prediction={data.prediction} />
      <div className="chart-key">
        <span className="green">━ Observed</span>
        <span>┄ Estimated</span>
        <small>Model estimate</small>
      </div>
    </Panel>
  );
}
export function ReadinessDetails({ data }: { data: Dashboard }) {
  const state = data.state!;
  return (
    <Panel>
      <PanelTitle
        title="Your recovery pattern"
        note="The signals behind the estimate"
      />
      <ReadinessChart
        data={data.history}
        cuts={state.readiness.cuts ?? [17, 33, 50, 67, 83]}
      />
      <div className="contributions">
        {Object.entries(state.readiness.contributions).map(([name, n]) => (
          <div key={name}>
            <span>{humanize(name)}</span>
            <div className="contribution-track">
              <i
                className={n < 0 ? "negative" : ""}
                style={{ width: `${Math.min(100, Math.abs(n) * 20)}%` }}
              />
            </div>
            <b>
              {n > 0 ? "+" : ""}
              {value(n, 2)}
            </b>
          </div>
        ))}
      </div>
      <details className="disclosure">
        <summary>How your estimate is calculated</summary>
        <p>
          Contributions are standardized relative to your baseline. They
          describe patterns, not causes. Personal calibration:{" "}
          {value(state.baseline_summary.shrinkage_weight * 100)}%.
        </p>
        <p>
          {state.readiness.degraded_reason
            ? `${state.readiness.degraded_reason}. Confidence is reduced.`
            : "Your recent sleep, HRV and resting pattern are available."}
        </p>
        <dl className="definition-list">
          <div>
            <dt>Recovery time constant</dt>
            <dd>{value(state.baseline_summary.recovery_tau_s, 1)} s</dd>
          </div>
          <div>
            <dt>Recorded recovery sessions</dt>
            <dd>{value(state.baseline_summary.tau_fit_n_sessions)}</dd>
          </div>
          <div>
            <dt>Average held-out error</dt>
            <dd>{value(state.baseline_summary.tau_fit_rmse, 2)} bpm</dd>
          </div>
        </dl>
        <p>
          Recovery bands show twice the held-out error, not a clinical
          confidence interval.
        </p>
        <button
          className="button"
          onClick={async () => {
            try {
              await post("/api/baseline/recompute");
              data.reset();
              data.notify("Your recovery pattern has been updated.");
            } catch {
              data.notify(
                "Could not update your recovery pattern. Please try again.",
              );
            }
          }}
        >
          Recalibrate my twin
        </button>
      </details>
    </Panel>
  );
}
export type PlanActions = {
  reminder: number;
  setReminder: (n: number) => void;
  adding: string;
  added: string[];
  book: (id: string) => Promise<void>;
};
export function PlanPanel({
  data,
  actions,
}: {
  data: Dashboard;
  actions: PlanActions;
}) {
  const plan = data.plan;
  const clock = (s: string) =>
    new Date(s).toLocaleTimeString(undefined, {
      hour: "numeric",
      minute: "2-digit",
      timeZone: plan?.timezone,
    });
  return (
    <Panel className="plan-panel">
      <PanelTitle
        title="Make time for you"
        note={
          plan?.calendar_status === "connected"
            ? "Your calendar is connected"
            : plan?.calendar_status === "demo"
              ? "Example schedule"
              : "Connect a calendar to find free time"
        }
      >
        <button
          className="icon-btn"
          aria-label="Refresh daily plan"
          disabled={data.loadingPlan || data.status !== "online"}
          onClick={data.refreshPlan}
        >
          <RefreshCw size={18} className={data.loadingPlan ? "spin" : ""} />
        </button>
      </PanelTitle>
      <div className="plan-items">
        {plan?.proposals.map((p) => (
          <article key={p.id} className="plan-item">
            <div
              className={`plan-symbol ${p.kind === "nap" ? "blue" : "green"}`}
            >
              {p.kind === "nap" ? <Moon size={19} /> : <Footprints size={19} />}
            </div>
            <div>
              <small>
                {clock(p.start)} — {clock(p.end)}
              </small>
              <h3>{p.title}</h3>
              <p>{p.reason}</p>
              <span className="pill">{humanize(p.intensity)}</span>
            </div>
            <button
              className="button book"
              aria-label={`${actions.added.includes(p.id) ? "Added" : "Add"} ${p.title} to calendar`}
              disabled={
                !!actions.adding ||
                actions.added.includes(p.id) ||
                data.status !== "online"
              }
              onClick={() => void actions.book(p.id)}
            >
              {actions.adding === p.id ? (
                <LoaderCircle size={16} className="spin" />
              ) : actions.added.includes(p.id) ? (
                <Check size={16} />
              ) : (
                <CalendarDays size={16} />
              )}
              <span>
                {actions.added.includes(p.id) ? "Added" : "Add to calendar"}
              </span>
            </button>
          </article>
        ))}
      </div>
      {!plan?.proposals.length && (
        <div className="empty-state">
          <CalendarDays size={26} />
          <p>
            {plan
              ? "No suitable windows are available right now. Refresh your plan or connect a calendar to find time."
              : "Gathering your schedule…"}
          </p>
        </div>
      )}
      <div className="plan-reminder">
        <label htmlFor="reminder">Remind me before an event</label>
        <select
          id="reminder"
          value={actions.reminder}
          onChange={(e) => actions.setReminder(Number(e.target.value))}
        >
          {[5, 10, 15, 30].map((n) => (
            <option key={n} value={n}>
              {n} minutes
            </option>
          ))}
        </select>
      </div>
    </Panel>
  );
}
export function CalendarDay({ data }: { data: Dashboard }) {
  return (
    <Panel>
      <PanelTitle title="Your day at a glance" note={data.plan?.timezone} />
      <div className="day-agenda">
        {data.plan?.busy.length ? (
          data.plan.busy.map((b, i) => (
            <div key={i}>
              <time>
                {new Date(b.start).toLocaleTimeString(undefined, {
                  hour: "numeric",
                  minute: "2-digit",
                  timeZone: data.plan!.timezone,
                })}
              </time>
              <i />
              <div>
                <b>{b.title}</b>
                <small>
                  Until{" "}
                  {new Date(b.end).toLocaleTimeString(undefined, {
                    hour: "numeric",
                    minute: "2-digit",
                    timeZone: data.plan!.timezone,
                  })}
                </small>
              </div>
            </div>
          ))
        ) : (
          <p>
            {data.plan?.calendar_status === "connected"
              ? "No busy windows today. Room for yourself."
              : "Connect your calendar to see your day here."}
          </p>
        )}
      </div>
      <div className="outlook-heading">
        <h3>Energy outlook</h3>
        <span className="pill">Scenario estimate</span>
      </div>
      <OutlookChart outlook={data.outlook} />
      <p className="fine-print">{data.outlook?.assumptions}</p>
    </Panel>
  );
}
export function LabPanel({ data }: { data: Dashboard }) {
  return (
    <Panel className="lab-panel">
      <PanelTitle
        title="A different kind of day"
        note="Explore what a change in pace could look like."
      />
      <div className="scenario-options">
        {[
          {
            id: "rest",
            name: "Take a breather",
            detail: "Pause & rest",
            icon: Leaf,
          },
          {
            id: "light",
            name: "Keep it light",
            detail: "Gentle movement",
            icon: Footprints,
          },
          {
            id: "exercise",
            name: "Get moving",
            detail: "An exercise scenario",
            icon: Activity,
          },
        ].map((s) => (
          <button
            key={s.id}
            disabled={!!data.scenarioBusy}
            aria-pressed={data.simulation?.scenario === s.id}
            onClick={() => data.simulate(s.id)}
            className={data.simulation?.scenario === s.id ? "selected" : ""}
          >
            <s.icon size={22} />
            <span>
              <b>{s.name}</b>
              <small>{s.detail}</small>
            </span>
            {data.scenarioBusy === s.id ? (
              <LoaderCircle size={16} className="spin" />
            ) : (
              <ArrowUpRight size={16} />
            )}
          </button>
        ))}
      </div>
      <div className="outlook-heading">
        <h3>
          {data.simulation
            ? "Possible heart-rate trajectory"
            : "Your current recovery"}
        </h3>
        <span className="pill">
          {data.simulation ? "Simulation" : "Estimate"}
        </span>
      </div>
      <RecoveryChart
        prediction={data.prediction}
        simulation={data.simulation}
      />
      <p className="fine-print">
        {data.simulation?.assumption ??
          data.prediction?.assumption ??
          "Add a recorded workout to explore a scenario."}
      </p>
      {data.simulation && (
        <button className="text-button" onClick={data.clearSimulation}>
          Return to recorded state
        </button>
      )}
    </Panel>
  );
}
