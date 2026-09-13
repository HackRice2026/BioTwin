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
