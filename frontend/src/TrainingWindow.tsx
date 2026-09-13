import {
  BatteryCharging,
  CalendarClock,
  Check,
  ChevronRight,
  Dumbbell,
  Star,
  TriangleAlert,
  X,
} from "lucide-react";
import type { TrainingDecision, TrainingScenario } from "./api";
import { Panel, PanelTitle } from "./DashboardPanels";
import type { Focus } from "./trainingFocus";

const clock = (iso: string, timeZone: string) =>
  new Date(iso).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZone,
  });

const duration = (minutes: number) =>
  minutes >= 60
    ? `${Math.floor(minutes / 60)}h ${minutes % 60}m`
    : `${minutes} min`;

export function BestWindowCard({
  decision,
  focus,
  onCompare,
}: {
  decision: TrainingDecision | null;
  focus: Focus;
  onCompare?: () => void;
}) {
  if (!decision) return null;
  if (!decision.available)
    return (
      <Panel className="window-card">
        <PanelTitle
          title="Best training window"
          note="Forecast, calendar and readiness"
        >
          <Dumbbell size={18} className="green" />
        </PanelTitle>
        <div className="empty-state">
          <CalendarClock size={22} />
          <p>{decision.reason}</p>
        </div>
      </Panel>
    );
  const w = decision.window,
    tz = decision.timezone;
  return (
    <Panel
      className={`window-card${focus?.kind === "window" ? " is-spoken" : ""}`}
    >
      <span className="eyebrow">
        <i />
        BEST TRAINING WINDOW
      </span>
      <h2 className="window-time">
        {clock(w.start, tz)} <span>–</span> {clock(w.end, tz)}
      </h2>
      <dl className="window-facts">
        <div>
          <dt>Projected energy</dt>
          <dd>{w.energy}</dd>
        </div>
        {decision.readiness != null && (
          <div>
            <dt>Readiness today</dt>
            <dd>{Math.round(decision.readiness)}</dd>
          </div>
        )}
        <div>
          <dt>Available time</dt>
          <dd>{w.minutes} min</dd>
        </div>
        <div>
          <dt>Workout</dt>
          <dd>
            {w.workout.title} · {w.workout.minutes} min
          </dd>
        </div>
        <div>
          <dt>Confidence</dt>
          <dd>{w.confidence}</dd>
        </div>
      </dl>
      <ul className="window-why" aria-label="Why this window">
        {w.reasons.map((reason) => (
          <li key={reason}>{reason}</li>
        ))}
      </ul>
      {onCompare && decision.scenarios.length > 1 && (
        <button className="text-button" onClick={onCompare}>
          Compare with training now or resting <ChevronRight size={14} />
        </button>
      )}
    </Panel>
  );
}

export function DayForecast({
  decision,
  focus,
}: {
  decision: TrainingDecision | null;
  focus: Focus;
}) {
  const curve = decision?.curve;
  if (!decision || !curve || curve.length < 2) return null;
  const tz = decision.timezone;
  const t0 = Date.parse(curve[0].time),
    t1 = Date.parse(curve[curve.length - 1].time);
  const x = (iso: string) =>
    Math.min(100, Math.max(0, ((Date.parse(iso) - t0) / (t1 - t0)) * 100));
  const y = (v: number) => 8 + (1 - v / 100) * 84;
  const valueAt = (ms: number) => {
    for (let i = 1; i < curve.length; i++) {
      const a = Date.parse(curve[i - 1].time),
        b = Date.parse(curve[i].time);
      if (ms <= b) {
        const f = Math.max(0, Math.min(1, (ms - a) / (b - a || 1)));
        return curve[i - 1].value + (curve[i].value - curve[i - 1].value) * f;
      }
    }
    return curve[curve.length - 1].value;
  };
  const line = (points: typeof curve) =>
    points
      .map((p, i) => `${i ? "L" : "M"}${x(p.time)} ${y(p.value)}`)
      .join(" ");
  // Solid only where a validated predictor is answering; the rhythm-only stretch is dashed.
  const firm = curve.findLastIndex((p) => p.confidence !== "Low");
  const solid = firm > 0 ? curve.slice(0, firm + 1) : [];
  const rhythm = curve.slice(Math.max(0, firm));
  const area = `${line(curve)} L100 100 L0 100 Z`;
  const window = decision.available ? decision.window : null;
  const windowX = window ? x(window.start) : null;
  const ticks = [0, 0.25, 0.5, 0.75, 1]
    .map((f) => {
      const ms = t0 + (t1 - t0) * f;
      return {
        left: f * 100,
        label: f === 0 ? "Now" : clock(new Date(ms).toISOString(), tz),
        value: Math.round(f === 0 ? decision.now!.energy : valueAt(ms)),
        best: false,
      };
    })
    .filter((t) => windowX == null || Math.abs(t.left - windowX) > 12);
  if (window && windowX != null)
    ticks.push({
      left: windowX,
      label: clock(window.start, tz),
      value: window.energy,
      best: true,
    });
  ticks.sort((a, b) => a.left - b.left);
  const riskFocus = focus?.kind === "risk" ? focus.index : -1;
  return (
    <Panel className="day-forecast">
      <PanelTitle
        title="Your day ahead"
        note={
          decision.calendar_status === "unavailable"
            ? "Projected energy · calendar not connected"
            : "Projected energy with your calendar"
        }
      >
        <BatteryCharging size={18} className="green" />
      </PanelTitle>
      <div
        className="day-chart"
        role="img"
        aria-label={`Projected energy ${decision.now?.energy} now${window ? `, ${window.energy} at the best window, ${clock(window.start, tz)}` : ""}.`}
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {(decision.risks ?? []).map((risk, index) => (
            <rect
              key={risk.start}
              className={`day-band risk${riskFocus === index ? " is-spoken" : ""}`}
              x={x(risk.start)}
              width={x(risk.end) - x(risk.start)}
              y={0}
              height={100}
            />
          ))}
          {window && (
            <rect
              className={`day-band window${focus?.kind === "window" ? " is-spoken" : ""}`}
              x={x(window.start)}
              width={Math.max(1.5, x(window.end) - x(window.start))}
              y={0}
              height={100}
            />
          )}
          <path className="day-area" d={area} />
          {solid.length > 1 && <path className="day-line" d={line(solid)} />}
          {rhythm.length > 1 && (
            <path className="day-line rhythm" d={line(rhythm)} />
          )}
        </svg>
        <span
          className="day-dot"
          style={{ left: "0%", top: `${y(curve[0].value)}%` }}
        />
        {window && windowX != null && (
          <>
            <span
              className={`day-star${focus?.kind === "window" ? " is-spoken" : ""}`}
              style={{ left: `${windowX}%`, top: `${y(window.energy)}%` }}
            >
              <Star size={13} fill="currentColor" />
            </span>
            <span className="day-best-label" style={{ left: `${windowX}%` }}>
              BEST
            </span>
          </>
        )}
      </div>
      {!!decision.busy?.length && (
      <div className="day-lane" aria-label="Busy on your calendar">
        {decision.busy.map((b) => (
          <i
            key={`${b.start}${b.title}`}
            title={`${b.title} · ${clock(b.start, tz)}–${clock(b.end, tz)}`}
            style={{
              left: `${x(b.start)}%`,
              width: `${Math.max(0.8, x(b.end) - x(b.start))}%`,
            }}
          />
        ))}
      </div>
      )}
      <div className="day-ticks">
        {ticks.map((t) => (
          <span
            key={`${t.left}${t.label}`}
            className={`${t.best ? "best" : ""}${t.left === 0 ? " first" : t.left === 100 ? " last" : ""}${!t.best && t.left !== 0 && t.left !== 100 ? " minor" : ""}`}
            style={{ left: `${t.left}%` }}
          >
            {t.label}
            <b>{t.value}</b>
          </span>
        ))}
      </div>
      <div className="chart-key">
        <span className="green">━ Forecast</span>
        <span>┄ Daily rhythm</span>
        <span className="amber">▬ Busy</span>
        <small>Garmin Body Battery · 0–100</small>
      </div>
      {!!decision.risks?.length && (
        <div className="day-notes">
          {decision.risks.map((risk, index) => (
            <div
              key={risk.start}
              className={`day-note risk${riskFocus === index ? " is-spoken" : ""}`}
            >
              <TriangleAlert size={14} className="red" />
              <b>
                {clock(risk.start, tz)}–{clock(risk.end, tz)}
              </b>
              <span>{risk.label}</span>
              <small>{risk.reasons.join(" · ")}</small>
            </div>
          ))}
        </div>
      )}
      {decision.recovery && (
        <div className="day-notes">
          <div className="day-note recovery">
            <BatteryCharging size={14} className="green" />
            <b>Recovery</b>
            <span>
              Back above {decision.recovery.threshold} in about{" "}
              {duration(decision.recovery.minutes)}
            </span>
            <small>{clock(decision.recovery.at, tz)}</small>
          </div>
          {decision.heart_rate_recovery_tau_s != null && (
            <small className="setup-note">
              After effort your heart rate settles with a{" "}
              {decision.heart_rate_recovery_tau_s}-second time constant. That
              describes heart rate, not energy.
            </small>
          )}
        </div>
      )}
      <details className="disclosure model-details">
        <summary>Forecast details · Validated with MATLAB</summary>
        <div className="model-rows">
          {decision.model_details.map((row) => (
            <div key={row.horizon} className={row.ml_wins ? "" : "baseline-wins"}>
              <small>{row.horizon} forecast</small>
              <b>
                {row.ml_wins
                  ? row.matlab_model
                  : `${row.baseline} baseline selected`}
              </b>
              {row.ml_wins ? (
                <p>
                  Model MAE {row.matlab_mae} · strong baseline{" "}
                  {row.baseline_mae}
                </p>
              ) : (
                <p>
                  It beats our ML models here: {row.baseline_mae} against{" "}
                  {row.matlab_mae} for {row.matlab_model}.
                </p>
              )}
              <p className="model-running">
                Running in BioTwin: {row.running} · MAE {row.running_mae}
              </p>
            </div>
          ))}
        </div>
        <p>
          Physiological forecasting is strongest from 30 minutes to 3 hours.
          Later in the day the plan leans on your hour-of-day rhythm and your
          calendar, not long-range precision. Errors are in Body Battery points.
        </p>
      </details>
    </Panel>
  );
}

function PathCard({
  option,
  timeZone,
  focused,
}: {
  option: TrainingScenario;
  timeZone: string;
  focused: boolean;
}) {
  return (
    <article
      className={`path-card${option.recommended ? " recommended" : ""}${focused ? " is-spoken" : ""}`}
    >
      <span className="eyebrow">
        {option.key === "now"
          ? "TRAIN NOW"
          : option.key === "rest"
            ? "REST"
            : clock(option.start!, timeZone)}
      </span>
      <dl className="window-facts compact">
        {option.energy != null && (
          <div>
            <dt>Energy at start</dt>
            <dd>{option.energy}</dd>
          </div>
        )}
        <div>
          <dt>Evening energy</dt>
          <dd>{option.evening_energy}</dd>
        </div>
        <div>
          <dt>Recovery load</dt>
          <dd className={`load-${option.recovery_load.toLowerCase()}`}>
            {option.recovery_load}
          </dd>
        </div>
      </dl>
      {option.recommended && (
        <span className="pill green">
          <Check size={12} />
          Recommended
        </span>
      )}
    </article>
  );
}

export function FuturePaths({
  decision,
  focus,
  onClose,
}: {
  decision: TrainingDecision | null;
  focus: Focus;
  onClose: () => void;
}) {
  if (!decision?.available || decision.scenarios.length < 2) return null;
  return (
    <Panel className="future-paths">
      <PanelTitle
        title="Future paths"
        note={`Where each choice leaves you by ${clock(decision.evening_at, decision.timezone)}`}
      >
        <button
          className="icon-btn"
          aria-label="Close comparison"
          onClick={onClose}
        >
          <X size={16} />
        </button>
      </PanelTitle>
      <div className="path-grid">
        {decision.scenarios.map((option) => (
          <PathCard
            key={option.key}
            option={option}
            timeZone={decision.timezone}
            focused={focus?.kind === "scenario" && focus.key === option.key}
          />
        ))}
      </div>
      <small className="setup-note">{decision.assumption}</small>
    </Panel>
  );
}
