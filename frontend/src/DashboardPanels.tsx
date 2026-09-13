import { useEffect, useState, type ReactNode } from "react";
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
  TrajectoryChart,
} from "./Charts";
import type { Topic } from "./topics";

export function currentMetricValue(
  field: string,
  data: Dashboard,
): number | null {
  const latest = data.state?.latest;
  if (!latest) return null;
  if (field === "sleep") {
    return latest.sleep?.total_minutes == null
      ? null
      : latest.sleep.total_minutes / 60;
  }
  return (
    (latest[field as keyof typeof latest] as number | null | undefined) ?? null
  );
}

export function hasCurrentMetric(field: string, data: Dashboard) {
  return currentMetricValue(field, data) != null;
}

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
  const n = currentMetricValue(field, data);
  if (n == null) return null;
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
  const breakdown = (extras[field] ?? []).filter(
    ([key]) => latest?.[key as keyof typeof latest] != null,
  );
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
      {breakdown.length > 0 && (
        <details className="disclosure">
          <summary>View breakdown</summary>
          <div className="signal-stats">
            {breakdown.map(([key, label]) => (
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
    score = r.score,
    day = data.plan?.date ?? r.computed_at.slice(0, 10),
    [completed, setCompleted] = useState<string[]>([]);
  useEffect(() => setCompleted([]), [day]);
  const workout = data.plan?.proposals.find((proposal) => proposal.kind === "workout");
  const nap = data.plan?.proposals.find((proposal) => proposal.kind === "nap");
  const sleepHours = Math.round((data.session?.user.profile.target_sleep ?? 480) / 60);
  const actions =
    score == null
      ? [
          {
            id: "baseline",
            title: "Build today's baseline",
            detail: "Wear your watch through the day so Forecast can personalize tomorrow.",
            icon: Activity,
            tone: "blue",
          },
          {
            id: "sleep",
            title: `Protect ${sleepHours} hours of sleep`,
            detail: "Set a wind-down time that makes your target sleep window realistic.",
            icon: Moon,
            tone: "blue",
          },
          {
            id: "hydrate",
            title: "Hydrate consistently",
            detail: "Keep water nearby and spread it through your day.",
            icon: Wind,
            tone: "green",
          },
        ]
      : score < 45
        ? [
            {
              id: "cardio",
              title: "Light cardio",
              detail: workout
                ? `${workout.title} is your calendar-aware movement option today.`
                : "Choose an easy walk, bike ride or mobility session; keep the effort light.",
              icon: Activity,
              tone: "green",
            },
            {
              id: "nap",
              title: "Power nap",
              detail: nap
                ? `${nap.title} is available in your plan. Keep it to the planned window.`
                : "Take a short early-afternoon reset if your schedule allows.",
              icon: Moon,
              tone: "blue",
            },
            {
              id: "sleep",
              title: `Protect ${sleepHours} hours of sleep`,
              detail: "Start your wind-down early and leave space to recharge tonight.",
              icon: Moon,
              tone: "blue",
            },
            {
              id: "hydrate",
              title: "Hydrate consistently",
              detail: "Keep water nearby and take regular breaks to drink.",
              icon: Wind,
              tone: "green",
            },
          ]
        : score < 65
          ? [
              {
                id: "cardio",
                title: "Light cardio",
                detail: workout
                  ? `${workout.title} fits your calendar and current body capacity.`
                  : "Use a steady, conversational-effort session today.",
                icon: Activity,
                tone: "green",
              },
              {
                id: "focus",
                title: "Schedule one focus block",
                detail: "Use your strongest part of the day for one important task.",
                icon: Flame,
                tone: "amber",
              },
              {
                id: "sleep",
                title: `Keep your ${sleepHours}-hour sleep target`,
                detail: "A consistent sleep window supports tomorrow's forecast.",
                icon: Moon,
                tone: "blue",
              },
              {
                id: "hydrate",
                title: "Hydrate consistently",
                detail: "Keep water nearby and take regular breaks to drink.",
                icon: Wind,
                tone: "green",
              },
            ]
          : [
              {
                id: "cardio",
                title: "Heavy cardio",
                detail: workout
                  ? `${workout.title} is the intensity your plan supports today.`
                  : "Use today for your harder training session if it fits your schedule.",
                icon: Activity,
                tone: "green",
              },
              {
                id: "focus",
                title: "Use a high-focus block",
                detail: "Put your most demanding work in a protected calendar window.",
                icon: Flame,
                tone: "amber",
              },
              {
                id: "sleep",
                title: `Keep your ${sleepHours}-hour sleep target`,
                detail: "Finish your training and work with enough room to wind down.",
                icon: Moon,
                tone: "blue",
              },
              {
                id: "hydrate",
                title: "Hydrate consistently",
                detail: "Support your activity by drinking regularly through the day.",
                icon: Wind,
                tone: "green",
              },
            ];
  const drivers = Object.entries(r.contributions)
    .sort(([, left], [, right]) => Math.abs(right) - Math.abs(left))
    .slice(0, 2)
    .map(([name, contribution]) =>
      `${humanize(name)} ${contribution >= 0 ? "supports" : "limits"} today's load`,
    );
  return (
    <Panel className="readiness-panel forecast-panel">
      <PanelTitle title="Forecast" note="Data into actionable steps">
        <Leaf size={19} className="green" />
      </PanelTitle>
      <div className="forecast-summary">
        <div>
          <span className="pill green">
            {score == null ? "Getting to know you" : humanize(r.state)}
          </span>
          <h3>{score == null ? "Your first plan starts here." : `${value(score)} body capacity`}</h3>
          <p>{drivers.length ? drivers.join(" · ") : "Forecast will adapt as more wearable data arrives."}</p>
        </div>
        <span className="forecast-progress">
          {completed.length}/{actions.length} done
        </span>
      </div>
      <div className="forecast-heading">
        <div>
          <span>According to today’s data</span>
          <h3>Your assignments</h3>
        </div>
        <small>{value(r.confidence * 100)}% confidence</small>
      </div>
      <div className="forecast-actions" role="list" aria-label="Today's Forecast assignments">
        {actions.map((action) => {
          const done = completed.includes(action.id);
          const Icon = action.icon;
          return (
            <button
              key={action.id}
              className={`forecast-action ${done ? "complete" : ""}`}
              type="button"
              role="listitem"
              aria-pressed={done}
              onClick={() =>
                setCompleted((items) =>
                  items.includes(action.id)
                    ? items.filter((item) => item !== action.id)
                    : [...items, action.id],
                )
              }
            >
              <span className={`forecast-action-icon ${action.tone}`}>
                {done ? <Check size={16} /> : <Icon size={16} />}
              </span>
              <span className="forecast-action-copy">
                <b>{action.title}</b>
                <small>{action.detail}</small>
              </span>
              <span className="forecast-action-state">{done ? "Done" : "Start"}</span>
            </button>
          );
        })}
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
export function TomorrowPanel({ data }: { data: Dashboard }) {
  const trajectory = data.trajectory;
  return (
    <Panel>
      <PanelTitle title="Ready for tomorrow" note="Forecasted body capacity">
        <Battery size={18} className="green" />
      </PanelTitle>
      {trajectory?.available ? (
        <>
          <div className="forecast-chart">
            <TrajectoryChart
              measured={trajectory.measured}
              points={trajectory.points}
            />
          </div>
          <div className="chart-key">
            <span className="green">━ Observed</span>
            <span>┄ Predicted</span>
            <small>
              {trajectory.basis === "model"
                ? "Ridge model · your daily rhythm"
                : "Your daily rhythm"}
            </small>
          </div>
        </>
      ) : (
        <div className="empty-state">
          <Battery size={22} />
          <p>
            {trajectory?.reason ??
              "Waiting for a Body Battery reading from your watch."}
          </p>
        </div>
      )}
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
              ? plan.explanation ||
                "No suitable windows are available right now. Refresh your plan to check again."
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
      <PanelTitle title="Energy outlook" note={data.plan?.timezone} />
      <div className="outlook-heading">
        <span className="pill">Scenario estimate</span>
      </div>
      <OutlookChart outlook={data.outlook} />
      <p className="fine-print">{data.outlook?.assumptions}</p>
    </Panel>
  );
}
