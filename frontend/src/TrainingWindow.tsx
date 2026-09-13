import { useEffect, useRef, useState } from "react";
import {
  BatteryCharging,
  CalendarClock,
  Check,
  ChevronRight,
  CircleHelp,
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

const signed = (n: number) => `${n > 0 ? "+" : ""}${n.toFixed(2)}`;

function WindowHelp({
  decision,
}: {
  decision: Extract<TrainingDecision, { available: true }>;
}) {
  const [open, setOpen] = useState(false);
  const w = decision.window,
    s = w.score;
  const rows: [string, number, string][] = s
    ? [
        ["Projected energy", s.terms.energy, `60% weight · energy ${w.energy} at the start`],
        ["Time of day", s.terms.time_of_day, "15% weight · preference peaks around 5 PM"],
        ["Forecast confidence", s.terms.confidence, `15% weight · ${w.confidence.toLowerCase()} at that hour`],
        ["Free time", s.terms.free_time, `10% weight · ${w.minutes} free minutes`],
        ...(s.terms.high_load_penalty
          ? ([["High-load penalty", s.terms.high_load_penalty, "overlaps a high-load stretch"]] as [string, number, string][])
          : []),
      ]
    : [];
  return (
    <span
      className={`help-tip${open ? " open" : ""}`}
      onMouseLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="help-trigger"
        aria-label="How this window was calculated"
        aria-expanded={open}
        aria-describedby="window-help"
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(e) => e.key === "Escape" && setOpen(false)}
        onBlur={() => setOpen(false)}
      >
        <CircleHelp size={15} />
      </button>
      <span className="help-popover" role="tooltip" id="window-help">
        <b>How this window was chosen</b>
        <span className="help-copy">
          Every free start between waking and three hours before bedtime was
          scored, skipping anything within 10 minutes of a calendar entry. The
          highest score wins.
        </span>
        {s && (
          <span className="help-rows">
            {rows.map(([label, value, detail]) => (
              <span key={label} className="help-row">
                <span>
                  {label}
                  <small>{detail}</small>
                </span>
                <em>{signed(value)}</em>
              </span>
            ))}
            <span className="help-row total">
              <span>
                Score
                <small>best of {s.candidates} possible starts</small>
              </span>
              <em>{s.total.toFixed(2)}</em>
            </span>
          </span>
        )}
        <span className="help-copy muted">
          Weights are engineering choices, not a fitted model. Effort is capped
          by readiness and projected energy.
        </span>
      </span>
    </span>
  );
}

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
      <div className="window-eyebrow">
        <span className="eyebrow">
          <i />
          BEST TRAINING WINDOW
        </span>
        <WindowHelp decision={decision} />
      </div>
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
  const laneRef = useRef<HTMLDivElement>(null);
  const [laneWidth, setLaneWidth] = useState(560);
  const hasCurve = !!curve && curve.length >= 2;
  useEffect(() => {
    const lane = laneRef.current;
    if (!lane || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) =>
      setLaneWidth(entry.contentRect.width || 560),
    );
    observer.observe(lane);
    return () => observer.disconnect();
  }, [hasCurve]);
  if (!decision || !curve || !hasCurve) return null;
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
  const gridValues = [100, 75, 50, 25, 0];
  // Each title runs past its (often short) block, so rows are packed by where the text
  // ends, measured against the lane's real width. Titles near the right edge sit to the
  // block's left instead. Past three rows an entry keeps its block and hover title only.
  const rowEnds: number[] = [];
  const events = (decision.busy ?? []).map((b) => {
    const left = x(b.start);
    const width = Math.max(1.2, x(b.end) - left);
    const labelPct = ((b.title.length * 5.4 + 16) / Math.max(laneWidth, 1)) * 100;
    const flip = left + labelPct > 100;
    const from = flip ? Math.max(0, left + width - labelPct - width) : left;
    const reach = (flip ? left + width : Math.max(left + width, left + labelPct)) + 0.8;
    let row = rowEnds.findIndex((end) => end <= from);
    if (row === -1 && rowEnds.length < 3) row = rowEnds.length;
    if (row >= 0) rowEnds[row] = reach;
    return { ...b, left, width, flip, row: Math.max(row, 0), labelled: row >= 0 };
  });
  const eventRows = Math.max(1, rowEnds.length);
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
      <div className="day-plot">
      <div className="day-axis" aria-hidden="true">
        {gridValues.map((v) => (
          <span key={v} style={{ top: `${y(v)}%` }}>
            {v}
          </span>
        ))}
      </div>
      <div className="day-main" ref={laneRef}>
      <div
        className="day-chart"
        role="img"
        aria-label={`Projected energy ${decision.now?.energy} now${window ? `, ${window.energy} at the best window, ${clock(window.start, tz)}` : ""}.`}
      >
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
          {gridValues.map((v) => (
            <line key={v} className="day-grid" x1={0} x2={100} y1={y(v)} y2={y(v)} />
          ))}
          {events.map((b) => (
            <rect
              key={`band${b.start}${b.title}`}
              className="day-band busy"
              x={b.left}
              width={b.width}
              y={0}
              height={100}
            />
          ))}
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
      {events.length > 0 && (
        <div
          className="day-events"
          aria-label="Your calendar on this timeline"
          style={{ height: `${eventRows * 24 - 4}px` }}
        >
          {events.map((b) => (
            <span
              key={`${b.start}${b.title}`}
              className={`day-event${b.flip ? " flip" : ""}`}
              title={`${b.title} · ${clock(b.start, tz)}–${clock(b.end, tz)}`}
              style={{
                left: `${b.left}%`,
                width: `${b.width}%`,
                top: `${b.row * 24}px`,
              }}
            >
              {b.labelled && <b>{b.title}</b>}
            </span>
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
      </div>
      </div>
      <div className="chart-key">
        <span className="green">━ Forecast</span>
        <span>┄ Daily rhythm</span>
        <span className="amber">▬ Calendar</span>
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
