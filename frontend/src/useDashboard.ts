import { useEffect, useRef, useState } from "react";
import {
  api,
  post,
  type MetricPoint,
  type SleepPoint,
  type Session,
  type Forecast,
  type Trajectory,
} from "./api";
import type {
  DailyPlan,
  DayOutlook,
  Readiness,
  RecoveryPrediction,
} from "./contracts";
import { useTwin } from "./transport";
import { useCalendar } from "./useCalendar";

export const metricNames = [
  "heart_rate_bpm",
  "hrv_rmssd_ms",
  "resting_hr_bpm",
  "respiration_brpm",
  "spo2_pct",
  "steps",
  "stress_level",
  "body_battery_pct",
  "distance_meters",
  "floors_ascended",
  "active_kcal",
  "max_hr_bpm",
  "min_hr_bpm",
];
const emptyMetrics = () =>
  Object.fromEntries(metricNames.map((m) => [m, [] as MetricPoint[]]));
export function useDashboard() {
  const [accountKey, setAccountKey] = useState(0);
  const [session, setSession] = useState<Session | null>(null);
  const twin = useTwin(accountKey);
  const { status, bundle, state } = twin;
  const calendar = useCalendar(session, status === "online", accountKey);
  const [days, setDays] = useState(7);
  const [metrics, setMetrics] = useState(emptyMetrics);
  const [sleep, setSleep] = useState<SleepPoint[]>([]);
  const [history, setHistory] = useState<Readiness[]>([]);
  const [predictions, setPredictions] = useState<RecoveryPrediction[]>([]);
  const [plan, setPlan] = useState<DailyPlan | null>(null);
  const [outlook, setOutlook] = useState<DayOutlook | null>(null);
  const [forecast, setForecast] = useState<Forecast | null>(null);
  const [trajectory, setTrajectory] = useState<Trajectory | null>(null);
  const [notice, notify] = useState("");
  const [loadingPlan, setLoadingPlan] = useState(false);
  const revision = useRef(0);
  function reset() {
    revision.current++;
    setSession(null);
    setMetrics(emptyMetrics());
    setSleep([]);
    setHistory([]);
    setPredictions([]);
    setForecast(null);
    setTrajectory(null);
    setPlan(null);
    setOutlook(null);
    setAccountKey((k) => k + 1);
  }
  useEffect(() => {
    let cancelled = false;
    api<Session>("/api/session")
      .then((s) => {
        if (!cancelled) setSession(s);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [accountKey, status]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => notify(""), 10000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (status === "offline" && bundle) {
      setMetrics(
        Object.fromEntries(
          Object.entries(bundle.metrics).map(([k, v]) => [k, v.series]),
        ),
      );
      setSleep(bundle.sleep.series);
      setHistory(bundle.readiness);
      setPredictions(bundle.predictions);
      setPlan(bundle.plan);
      setOutlook(bundle.outlook);
      return;
    }
    if (status !== "online") return;
    let stopped = false;
    const controller = new AbortController();
    const load = async () => {
      void api<Forecast>("/api/forecast", { signal: controller.signal })
        .then((result) => {
          if (!stopped) setForecast(result);
        })
        .catch(() => {
          if (!stopped) notify("Battery forecast could not refresh.");
        });
      void api<Trajectory>("/api/forecast/trajectory", { signal: controller.signal })
        .then((result) => {
          if (!stopped) setTrajectory(result);
        })
        .catch(() => {
          if (!stopped) notify("Battery Broadcast could not refresh.");
        });
      const metricRequests = metricNames.map(async (metric) => {
        const result = await api<{ series: MetricPoint[] }>(
          `/api/metrics?metric=${metric}&days=${days}`,
          { signal: controller.signal },
        );
        if (!stopped)
          setMetrics((current) => ({ ...current, [metric]: result.series }));
      });
      const sleepRequest = api<{ series: SleepPoint[] }>(
        `/api/metrics?metric=sleep&days=${days}`,
        { signal: controller.signal },
      ).then((result) => {
        if (!stopped) setSleep(result.series);
      });
      const requests = [
        "/api/readiness/history",
        "/api/predictions",
        "/api/plan/today",
        "/api/outlook",
      ];
      const [metricResults, sleepResult, results] = await Promise.all([
        Promise.allSettled(metricRequests),
        Promise.allSettled([sleepRequest]).then(([result]) => result),
        Promise.allSettled(requests.map((path) =>
          api<unknown>(path, { signal: controller.signal }),
        )),
      ]);
      if (stopped) return;
      const [h, p, pl, out] = results;
      if (h.status === "fulfilled") setHistory(h.value as Readiness[]);
      if (p.status === "fulfilled")
        setPredictions(p.value as RecoveryPrediction[]);
      if (pl.status === "fulfilled") setPlan(pl.value as DailyPlan);
      if (out.status === "fulfilled") setOutlook(out.value as DayOutlook);
      if (
        metricResults.some((result) => result.status === "rejected") ||
        sleepResult.status === "rejected" ||
        results.some((result) => result.status === "rejected")
      )
        notify(
          "Some measurements could not refresh. Please try again shortly.",
        );
    };
    void load();
    const timer = setInterval(load, 60000);
    return () => {
      stopped = true;
      controller.abort();
      clearInterval(timer);
    };
  }, [status, bundle, accountKey, days]);
  async function refreshPlan() {
    const current = revision.current;
    setLoadingPlan(true);
    try {
      const p = await post<DailyPlan>("/api/plan/refresh");
      if (current === revision.current) setPlan(p);
    } catch {
      notify(
        "Your calendar could not refresh. Check your connection and try again.",
      );
    } finally {
      setLoadingPlan(false);
    }
  }
  function series(field: string): MetricPoint[] {
    const rows = metrics[field] ?? [];
    const q = state?.quality?.[field];
    const reading =
      state?.latest?.[field as keyof NonNullable<typeof state.latest>];
    if (
      !q ||
      typeof reading !== "number" ||
      (rows.at(-1)?.time ?? "") >= q.event_time
    )
      return rows;
    return [
      ...rows.slice(-999),
      {
        time: q.event_time,
        value: reading,
        provenance: q.provenance,
        confidence: q.confidence,
      },
    ];
  }
  const prediction = state?.prediction?.curve.length
    ? state.prediction
    : predictions[0];
  return {
    ...twin,
    session,
    accountKey,
    reset,
    days,
    setDays,
    metrics,
    series,
    sleep,
    history,
    plan,
    outlook,
    forecast,
    trajectory,
    prediction,
    notice,
    notify,
    loadingPlan,
    refreshPlan,
    calendar,
  };
}
export type Dashboard = ReturnType<typeof useDashboard>;
