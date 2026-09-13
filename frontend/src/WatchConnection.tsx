import { useEffect, useState } from "react";
import { api, post, value } from "./api";
import type { TwinState } from "./contracts";

const metrics = [
  ["heart_rate_bpm", "Heart rate", "bpm"],
  ["steps", "Steps today", ""],
  ["stress_level", "Garmin stress", "/ 100"],
  ["body_battery", "Body Battery", "/ 100"],
  ["spo2_pct", "Pulse Ox", "%"],
  ["total_calories", "Total calories today", "kcal"],
  ["distance_m", "Distance today", "m"],
  ["floors_climbed", "Floors today", ""],
  ["acceleration_mg", "Acceleration incl. gravity", "mg"],
];
type WatchStatus = {
  paired: boolean;
  sync: { received_at: string } | null;
  readings: Record<string, { value: number; event_time: string }>;
};
function age(stamp: string) {
  const seconds = Math.max(0, Math.floor((Date.now() - Date.parse(stamp)) / 1000));
  return seconds < 60 ? `${seconds}s ago` : seconds < 3600
    ? `${Math.floor(seconds / 60)}m ago` : `${Math.floor(seconds / 3600)}h ago`;
}
export default function WatchConnection({ personal, setup = false, onAuth, state }: {
  personal: boolean; setup?: boolean; onAuth?: () => void; state?: TwinState;
}) {
  const [status, setStatus] = useState<WatchStatus | null>(null);
  const [token, setToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!personal) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const next = await api<WatchStatus>("/api/watch");
        if (!stopped) { setStatus(next); setError(""); }
      } catch (e) {
        if (!stopped) setError((e as Error).message);
      } finally {
        if (!stopped) timer = setTimeout(refresh, 5000);
      }
    }
    void refresh();
    return () => { stopped = true; clearTimeout(timer); };
  }, [personal]);
  async function pair() {
    if (!personal) { onAuth?.(); return; }
    setBusy(true);
    try {
      const result = await post<{ token: string }>("/api/watch/token");
      setToken(result.token);
      setStatus(await api<WatchStatus>("/api/watch"));
      setError("");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  async function revoke() {
    setBusy(true);
    try {
      await api("/api/watch/token", { method: "DELETE" });
      setToken("");
      setStatus(await api<WatchStatus>("/api/watch"));
      setError("");
    } catch (e) { setError((e as Error).message); }
    finally { setBusy(false); }
  }
  if (!setup && (!personal || (!status?.paired && !status?.sync))) return null;
  const receiving = !error && status?.paired && status.sync
    && Date.now() - Date.parse(status.sync.received_at) < 20000;
  return <section className="card watch-connection">
    <span className="eyebrow">VENU 2 · CONNECT IQ</span>
    <h3>{receiving ? "Receiving from your watch" : "Watch stream"}</h3>
    <p role="status">{error ? "Connection check failed" : receiving ? "Connected"
      : status?.paired ? "Waiting for the watch app" : "Watch is not paired"}
      {status?.sync && ` · Last delivery ${age(status.sync.received_at)}`}</p>
    <p>Keep BioTwin open on your watch and Garmin Connect available on your paired phone.
      Updates are requested every 5 seconds; phone and network delays can add time.
      Stress, Body Battery and Pulse Ox update when Garmin records a new sample.</p>
    {error && <p className="notice" role="alert">{error}</p>}
    <dl className="watch-readings">
      {metrics.map(([key, label, unit]) => {
        // Use socket updates immediately when CIQ is the selected source. The
        // status endpoint also preserves watch values when another source wins.
        let reading = status?.readings[key];
        const quality = state?.quality?.[key];
        const current = state?.latest?.[key as keyof NonNullable<TwinState["latest"]>];
        if (quality?.provenance === "garmin_ciq_live" && typeof current === "number"
          && (!reading || Date.parse(quality.event_time) >= Date.parse(reading.event_time))) {
          reading = { value: current, event_time: quality.event_time };
        }
        return <div key={key}>
          <dt>{label}</dt>
          <dd>{value(reading?.value)} <small>{reading ? unit : ""}</small></dd>
          <small>{reading ? `Measured ${age(reading.event_time)}` : "Not reported"}</small>
        </div>;
      })}
    </dl>
    {setup && <>
      <div className="watch-actions">
        <button className="button" onClick={pair} disabled={busy}>
          {status?.paired ? "Replace pairing token" : "Create pairing token"}
        </button>
        {status?.paired && <button className="button" onClick={revoke} disabled={busy}>Revoke watch access</button>}
      </div>
      <p>Tokens can only send watch measurements, expire after 90 days, and are shown once.
        Replacing a token disconnects the previous watch build.</p>
      {token && <label>Pairing token — save in watch-app/.env as API_KEY
        <input aria-label="Watch pairing token" type="password" readOnly value={token}
          onFocus={(e) => e.target.select()} autoComplete="off" />
      </label>}
    </>}
  </section>;
}
