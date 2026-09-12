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
export type Session = {
  user: { id: string; name: string; email: string; profile: Profile };
  demo: boolean;
  voice_configured: boolean;
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
