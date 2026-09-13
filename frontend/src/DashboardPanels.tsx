import { type ReactNode } from "react";
import {
  Activity,
  ArrowUpRight,
  Battery,
  CalendarDays,
  Check,
  Flame,
  Footprints,
  Heart,
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
  title: ReactNode;
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
  const extras: Record<
    string,
    { key: keyof NonNullable<typeof latest>; label: string; unit?: string; divisor?: number }[]
  > = {
    active_kcal: [
      { key: "total_calories", label: "Total calories", unit: "kcal" },
      { key: "active_seconds", label: "Active time", unit: "min", divisor: 60 },
      { key: "highly_active_seconds", label: "Highly active", unit: "min", divisor: 60 },
    ],
    steps: [
      { key: "moderate_intensity_min", label: "Moderate", unit: "min" },
      { key: "vigorous_intensity_min", label: "Vigorous", unit: "min" },
    ],
    stress_level: [
      { key: "stress_avg", label: "Daily average", unit: "/100" },
      { key: "stress_max", label: "Daily maximum", unit: "/100" },
      { key: "stress_high_min", label: "High", unit: "min" },
      { key: "stress_medium_min", label: "Medium", unit: "min" },
      { key: "stress_low_min", label: "Low", unit: "min" },
    ],
    body_battery_pct: [
      { key: "body_battery_at_wake", label: "At wake", unit: "/100" },
      { key: "body_battery_charged", label: "Charged", unit: "points" },
      { key: "body_battery_drained", label: "Drained", unit: "points" },
    ],
  };
  const latestSleep = data.sleep.at(-1)?.value;
  const breakdown = field === "sleep"
    ? [
        { label: "Sleep score", value: latestSleep?.score, unit: "/100" },
        { label: "Total", value: latestSleep?.total_minutes != null ? latestSleep.total_minutes / 60 : null, unit: "hrs" },
        { label: "Deep", value: latestSleep?.deep_minutes, unit: "min" },
        { label: "Light", value: latestSleep?.light_minutes, unit: "min" },
        { label: "REM", value: latestSleep?.rem_minutes, unit: "min" },
        { label: "Awake", value: latestSleep?.awake_minutes, unit: "min" },
      ].filter((item) => item.value != null)
    : (extras[field] ?? []).flatMap((item) => {
        const raw = latest?.[item.key];
        return typeof raw === "number"
          ? [{ label: item.label, value: raw / (item.divisor ?? 1), unit: item.unit }]
          : [];
      });
  const source = q?.provenance ?? data.sleep.at(-1)?.provenance;
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
              ? `Recorded ${new Date(q.event_time).toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" })}${source ? ` · ${humanize(source)}` : ""}`
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
      {field === "hrv_rmssd_ms" && rows.length === 0 && (
        <p className="notice">
          HRV RMSSD is not present in this Garmin export. BioTwin does not substitute another variability score.
        </p>
      )}
      {breakdown.length > 0 && (
        <details className="disclosure">
          <summary>View breakdown</summary>
          <div className="signal-stats">
            {breakdown.map((item) => (
              <div key={item.label}>
                <small>{item.label}</small>
                <b>
                  {value(item.value, item.unit === "hrs" ? 1 : 0)}{" "}
                  {item.unit && <em>{item.unit}</em>}
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
                  ? `${workout.title} fits your calendar and current readiness.`
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
    <Panel className="readiness-panel forecast-panel current-battery-panel">
      <PanelTitle
        title={
          <span className="current-battery-title">
            <span>Current Body Battery</span>
            <span
              className="current-battery-meter"
              role="img"
              aria-label={
                score == null
                  ? "Body Battery is awaiting a reading"
                  : `Body Battery ${value(score)} percent`
              }
            >
              <span className="current-battery-meter-fill" aria-hidden="true">
                <i style={{ width: `${score == null ? 0 : value(score)}%` }} />
              </span>
              <Battery aria-hidden="true" />
              <b aria-hidden="true">{score == null ? "—" : `${value(score)}%`}</b>
            </span>
          </span>
        }
        note="BioTwin estimate of your energy reserve"
      />
      <div className="forecast-summary current-battery-summary">
        <div>
          <span className="pill green">
            {score == null ? "Getting to know you" : humanize(r.state)}
          </span>
          <h3>{score == null ? "Your first plan starts here." : "Readiness for today"}</h3>
          <p>{drivers.length ? drivers.join(" · ") : "Forecast will adapt as more wearable data arrives."}</p>
        </div>
      </div>
      <div className="forecast-heading recommendation-heading">
        <div>
          <span>Support your energy</span>
          <h3>Today’s recommendations</h3>
        </div>
        <small>{value(r.confidence * 100)}% confidence</small>
      </div>
      <div className="forecast-recommendations" role="region" aria-label="Readiness recommendations">
        <div className="forecast-actions" role="list" aria-label="Today's recommendations">
        {actions.map((action) => {
          const Icon = action.icon;
          return (
            <article
              key={action.id}
              className="forecast-action"
              role="listitem"
            >
              <span className={`forecast-action-icon ${action.tone}`}>
                <Icon size={16} />
              </span>
              <span className="forecast-action-copy">
                <b>{action.title}</b>
                <small>{action.detail}</small>
              </span>
            </article>
          );
        })}
        </div>
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
    <Panel className="body-battery-forecast-panel">
      <PanelTitle title="Body Battery forecast" note="Your projected energy reserve">
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
          <p className="forecast-credibility">
            {trajectory.basis === "model"
              ? "From the ridge model fitted in MATLAB on your current level and recent trend."
              : "Your last reading was too old for the fitted model, so this uses your own hour-of-day rhythm instead."}
          </p>
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
