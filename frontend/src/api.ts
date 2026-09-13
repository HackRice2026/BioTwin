import type {
  TwinState,
  DailyPlan,
  RecoveryPrediction,
  Readiness,
  DayOutlook,
  SimulationOverlay,
} from "./contracts";

export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await fetch(path, {
    credentials: "include",
    ...options,
    headers: {
      ...(options.body instanceof FormData
        ? {}
        : { "Content-Type": "application/json" }),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const text = await response.text();
    let message = text;
    try {
      const data = JSON.parse(text);
      message =
        typeof data.detail === "string"
          ? data.detail
          : JSON.stringify(data.detail);
    } catch {
      /* Non-JSON proxy failures retain their response text. */
    }
    throw new Error(message || `Request failed (${response.status})`);
  }
  return response.json();
}
export const post = <T>(path: string, data: unknown = {}) =>
  api<T>(path, { method: "POST", body: JSON.stringify(data) });
export type MetricPoint = {
  time: string;
  value: number;
  provenance: string;
  confidence: number;
};
export type SleepPoint = {
  time: string;
  value: {
    start: string;
    end: string;
    total_minutes: number;
    awake_minutes?: number;
    light_minutes?: number;
    deep_minutes?: number;
    rem_minutes?: number;
    efficiency_pct?: number;
    score?: number;
  };
  provenance: string;
};
export type Forecast =
  | { available: false; reason: string; missing: string[] }
  | {
      available: true;
      horizon_minutes: number;
      current: number;
      forecast: number;
      validation_mae: number;
      measured_age_minutes: number;
      imputed_inputs: string[];
      model: string;
    };
export type Session = {
  user: { id: string; name: string; email: string; profile: Profile };
  demo: boolean;
  data_source: "sqlite" | "postgres" | "supabase" | "database";
  voice_configured: boolean;
  narration_configured: boolean;
  retention_days: number;
};
export type Profile = {
  timezone: string;
  bedtime: string;
  target_sleep: number;
  workout_minutes: number;
  naps_enabled: boolean;
  calendar_ids?: string[];
};
export type OfflineBundle = {
  simulations: Record<string, SimulationOverlay>;
  outlook: DayOutlook;
  states: TwinState[];
  plan: DailyPlan;
  metrics: Record<string, { series: MetricPoint[] }>;
  sleep: { series: SleepPoint[] };
  predictions: RecoveryPrediction[];
  readiness: Readiness[];
  answers: Record<string, string>;
};
export function humanize(value: string) {
  return value.replaceAll("_", " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
export function value(value: number | null | undefined, digits = 0) {
  return value == null
    ? "—"
    : value.toLocaleString(undefined, { maximumFractionDigits: digits });
}
export type TrajectoryPoint = {
  horizon_minutes: number;
  value: number;
  validation_mae: number;
  method: string;
  beats_baseline: boolean;
};
export type Trajectory =
  | { available: false; reason: string; missing: string[] }
  | {
      available: true;
      /** "model" when the ridge could run; "rhythm" when the current reading was
          too old for it and the hour-of-day climatology answered instead. */
      basis: "model" | "rhythm";
      current: number;
      measured_age_minutes: number;
      imputed_inputs: string[];
      measured: { minutes_ago: number; value: number }[];
      points: TrajectoryPoint[];
      reason?: string;
      note: string;
    };
export type TrainingScenario = {
  key: "now" | "best" | "rest";
  start: string | null;
  energy: number | null;
  evening_energy: number;
  recovery_load: "Low" | "Medium" | "High";
  intensity: string;
  recommended: boolean;
};
export type ModelDetail = {
  horizon: string;
  matlab_model: string;
  matlab_mae: number;
  baseline: string;
  baseline_mae: number;
  running: string;
  running_mae: number;
  ml_wins: boolean;
};
type DecisionDay = {
  now: { time: string; energy: number };
  curve: {
    time: string;
    minutes: number;
    value: number;
    confidence: "High" | "Moderate" | "Low";
    method: string;
  }[];
  busy: { start: string; end: string; title: string }[];
  risks: { start: string; end: string; label: string; reasons: string[] }[];
  recovery: {
    threshold: number;
    minutes: number;
    at: string;
    confidence: string;
  } | null;
  heart_rate_recovery_tau_s: number | null;
  readiness: number | null;
};
type DecisionBase = {
  issued_at: string;
  timezone: string;
  calendar_status: "connected" | "demo" | "unavailable";
  model_details: ModelDetail[];
  assumption: string;
};
/** GET /api/training-window -- decided by modeling/training_window.py; the coach
    narrates this same object, so nothing here is recomputed in the browser. */
export type TrainingDecision =
  | (DecisionBase &
      Partial<DecisionDay> & {
        available: false;
        reason: string;
        scenarios?: TrainingScenario[];
      })
  | (DecisionBase &
      DecisionDay & {
        available: true;
        window: {
          start: string;
          end: string;
          minutes: number;
          energy: number;
          confidence: "High" | "Moderate" | "Low";
          workout: { title: string; intensity: string; minutes: number };
          reasons: string[];
        };
        evening_at: string;
        scenarios: TrainingScenario[];
      });
export type SimulatePoint = {
  horizon_minutes: number;
  value: number;
  validation_mae: number;
};
export type DayScenario = {
  id:
    | "current_plan"
    | "train_now"
    | "train_best_window"
    | "extra_steps"
    | "recovery_break";
  label: string;
  summary: string;
  points: SimulatePoint[];
  decision: {
    best_window: string;
    workout: string;
    evening_state: number;
    activity_load: string;
  };
  confidence: "low" | "medium" | "high";
};
export type DaySimulation =
  | { available: false; reason: string }
  | {
      available: true;
      generated_at: string;
      basis: "model" | "rhythm";
      current: number;
      baseline: DayScenario;
      scenarios: DayScenario[];
      selected_scenario_id: DayScenario["id"];
      controls: {
        steps: number;
        step_min: number;
        step_max: number;
        recovery_minutes: number;
      };
      coach_summary: string;
      assumptions: string[];
    };
