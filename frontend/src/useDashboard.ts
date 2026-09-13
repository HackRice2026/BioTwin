import { useEffect, useRef, useState } from "react";
import { api, post, type MetricPoint, type SleepPoint, type Session } from "./api";
import type { DailyPlan, DayOutlook, Readiness, RecoveryPrediction, SimulationOverlay } from "./contracts";
import { useTwin } from "./transport";

export const metricNames = ["heart_rate_bpm", "hrv_rmssd_ms", "resting_hr_bpm", "respiration_brpm", "spo2_pct", "steps", "stress_level", "body_battery_pct", "distance_meters", "floors_ascended", "active_kcal", "max_hr_bpm", "min_hr_bpm"];
const emptyMetrics = () => Object.fromEntries(metricNames.map(m => [m, [] as MetricPoint[]]));
export function useDashboard() {
  const [accountKey, setAccountKey] = useState(0);
  const [session, setSession] = useState<Session | null>(null);
  const twin = useTwin(accountKey);
  const { status, bundle, state } = twin;
  const [days, setDays] = useState(7);
  const [metrics, setMetrics] = useState(emptyMetrics);
  const [sleep, setSleep] = useState<SleepPoint[]>([]);
  const [history, setHistory] = useState<Readiness[]>([]);
  const [predictions, setPredictions] = useState<RecoveryPrediction[]>([]);
  const [plan, setPlan] = useState<DailyPlan | null>(null);
  const [outlook, setOutlook] = useState<DayOutlook | null>(null);
  const [notice, notify] = useState("");
  const [loadingPlan, setLoadingPlan] = useState(false);
  const [simulation, setSimulation] = useState<SimulationOverlay | null>(null);
  const [scenarioBusy, setScenarioBusy] = useState("");
  const overlay = useRef<SimulationOverlay | null>(null);
  const revision = useRef(0);
  function reset() {
    revision.current++;
    setSession(null); setMetrics(emptyMetrics()); setSleep([]); setHistory([]);
    setPredictions([]); setPlan(null); setOutlook(null); clearSimulation();
    setAccountKey(k => k + 1);
  }
  function clearSimulation() { overlay.current = null; setSimulation(null); }
  useEffect(() => {
    let cancelled = false;
    api<Session>("/api/session").then(s => { if (!cancelled) setSession(s); }).catch(() => {});
    return () => { cancelled = true; };
  }, [accountKey, status]);
  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => notify(""), 10000);
    return () => clearTimeout(timer);
  }, [notice]);
  useEffect(() => {
    if (status === "offline" && bundle) {
      setMetrics(Object.fromEntries(Object.entries(bundle.metrics).map(([k, v]) => [k, v.series])));
      setSleep(bundle.sleep.series); setHistory(bundle.readiness); setPredictions(bundle.predictions);
      setPlan(bundle.plan); setOutlook(bundle.outlook); return;
    }
    if (status !== "online") return;
    let stopped = false;
    const controller = new AbortController();
    const load = async () => {
      const requests = [
        ...metricNames.map(m => `/api/metrics?metric=${m}&days=${days}`),
        `/api/metrics?metric=sleep&days=${days}`, "/api/readiness/history", "/api/predictions", "/api/plan/today", "/api/outlook",
      ];
      const results = await Promise.allSettled(requests.map(path => api<unknown>(path, { signal: controller.signal })));
      if (stopped) return;
      const next = emptyMetrics();
      metricNames.forEach((m, i) => { const r = results[i]; if (r.status === "fulfilled") next[m] = (r.value as { series: MetricPoint[] }).series; });
      setMetrics(next);
      const [s, h, p, pl, out] = results.slice(metricNames.length);
      if (s.status === "fulfilled") setSleep((s.value as { series: SleepPoint[] }).series);
      if (h.status === "fulfilled") setHistory(h.value as Readiness[]);
      if (p.status === "fulfilled") setPredictions(p.value as RecoveryPrediction[]);
      if (pl.status === "fulfilled") setPlan(pl.value as DailyPlan);
      if (out.status === "fulfilled") setOutlook(out.value as DayOutlook);
      if (results.some(r => r.status === "rejected")) notify("Some measurements could not refresh. Please try again shortly.");
    };
    void load(); const timer = setInterval(load, 60000);
    return () => { stopped = true; controller.abort(); clearInterval(timer); };
  }, [status, bundle, accountKey, days]);
  async function refreshPlan() {
    const current = revision.current;
    setLoadingPlan(true);
    try { const p = await post<DailyPlan>("/api/plan/refresh"); if (current === revision.current) setPlan(p); }
    catch { notify("Your calendar could not refresh. Check your connection and try again."); }
    finally { setLoadingPlan(false); }
  }
  async function simulate(scenario: string) {
    const current = revision.current;
    setScenarioBusy(scenario);
    try {
      const result = status === "offline" && bundle?.simulations[scenario]
        ? bundle.simulations[scenario]
        : await post<SimulationOverlay>("/api/simulate", { scenario });
      if (current === revision.current) { overlay.current = result; setSimulation(result); }
    } catch { notify("This scenario is unavailable. Connect your watch or import a recorded workout first."); }
    finally { setScenarioBusy(""); }
  }
  function series(field: string): MetricPoint[] {
    const rows = metrics[field] ?? [];
    const q = state?.quality?.[field];
    const reading = state?.latest?.[field as keyof NonNullable<typeof state.latest>];
    if (!q || typeof reading !== "number" || (rows.at(-1)?.time ?? "") >= q.event_time) return rows;
    return [...rows.slice(-999), { time: q.event_time, value: reading, provenance: q.provenance, confidence: q.confidence }];
  }
  const prediction = state?.prediction?.curve.length ? state.prediction : predictions[0];
  return { ...twin, session, accountKey, reset, days, setDays, metrics, series, sleep, history, plan, outlook, prediction, notice, notify, loadingPlan, refreshPlan, simulation, scenarioBusy, simulate, clearSimulation, overlay };
}
export type Dashboard = ReturnType<typeof useDashboard>;
