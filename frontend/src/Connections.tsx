import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Watch,
  CalendarDays,
  AudioLines,
  Upload,
  Check,
  ArrowUpRight,
  Bluetooth,
  Radio,
  RefreshCw,
  LogOut,
  Download,
  Trash2,
} from "lucide-react";
import { api, post } from "./api";
import type { Session, Profile } from "./api";

type Sources = {
  sources: {
    provider: string;
    status: string;
    configured: boolean;
    last_frame: string | null;
    sync?: { status: string; error?: string } | null;
  }[];
  elevenlabs: { configured: boolean; model: string };
};
export function AuthModal({
  onClose,
  onDone,
}: {
  onClose: () => void;
  onDone: () => void;
}) {
  const [register, setRegister] = useState(true),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false);
  async function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(e.currentTarget);
    try {
      await post(`/auth/session/${register ? "register" : "login"}`, {
        email: data.get("email"),
        password: data.get("password"),
        name: data.get("name") ?? "",
        adult: data.get("adult") === "on",
      });
      onDone();
      onClose();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop" onClick={onClose}>
      <section
        className="auth-modal"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
        aria-label="Your BioTwin account"
      >
        <button
          className="close"
          onClick={onClose}
          aria-label="Close account dialog"
        >
          ×
        </button>
        <span className="eyebrow">MAKE IT PERSONAL</span>
        <h2>{register ? "Meet your own twin." : "Welcome back."}</h2>
        <p>Your wearable data lives in your account, separate from the demo.</p>
        <form onSubmit={submit}>
          {register && (
            <label>
              Your name
              <input
                name="name"
                autoComplete="given-name"
                placeholder="First name"
                required
              />
            </label>
          )}
          <label>
            Email
            <input
              name="email"
              type="email"
              autoComplete="email"
              placeholder="you@example.com"
              required
            />
          </label>
          <label>
            Password
            <input
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              minLength={12}
              required
              placeholder="At least 12 characters"
            />
          </label>
          {register && (
            <label className="check-label">
              <input name="adult" type="checkbox" required /> I am 18 or older.
            </label>
          )}
          {error && (
            <p className="error" role="alert">
              {error}
            </p>
          )}
          <button className="button primary" disabled={busy}>
            {busy ? "Please wait…" : register ? "Create my twin" : "Sign in"}
            <ArrowUpRight size={16} />
          </button>
        </form>
        <button
          className="text-button"
          onClick={() => {
            setRegister(!register);
            setError("");
          }}
        >
          {register
            ? "Already have an account? Sign in"
            : "New to BioTwin? Create an account"}
        </button>
      </section>
    </div>
  );
}

export default function Connections({
  session,
  onAuth,
  onChange,
  notify,
}: {
  session: Session | null;
  onAuth: () => void;
  onChange: () => void;
  notify: (s: string) => void;
}) {
  const [sources, setSources] = useState<Sources | null>(null),
    [busy, setBusy] = useState(""),
    [profile, setProfile] = useState<Profile>(
      session?.user.profile ?? {
        timezone: "America/Chicago",
        bedtime: "23:00",
        target_sleep: 480,
        workout_minutes: 30,
        naps_enabled: true,
      },
    );
  const file = useRef<HTMLInputElement>(null);
  const bleDevice = useRef<{ gatt?: { disconnect: () => void } } | null>(null);
  const [broadcasting, setBroadcasting] = useState(false),
    [deleting, setDeleting] = useState(false);
  const [bleBridgeStatus, setBleBridgeStatus] = useState<{
    status: string;
    detail?: string;
  }>({ status: "stopped" });
  const [influxSyncStatus, setInfluxSyncStatus] = useState<{
    status: string;
    detail?: string;
    last_frame_at?: string;
  }>({ status: "stopped" });
  const reload = () =>
    api<Sources>("/sources")
      .then(setSources)
      .catch((e) => notify(e.message));
  const pollBridge = () =>
    api<{ status: string; detail?: string }>(
      "/api/connect/garmin-ble-bridge/status",
    )
      .then(setBleBridgeStatus)
      .catch(() => {});
  const pollInfluxSync = () =>
    api<{ status: string; detail?: string; last_frame_at?: string }>(
      "/api/connect/garmin-influx/live/status",
    )
      .then(setInfluxSyncStatus)
      .catch(() => {});
  useEffect(() => {
    reload();
    pollBridge();
    pollInfluxSync();
    const interval = setInterval(() => {
      pollBridge();
      pollInfluxSync();
    }, 3000);
    return () => {
      bleDevice.current?.gatt?.disconnect();
      clearInterval(interval);
    };
  }, []);
  async function connect(provider: string) {
    if (session?.demo) {
      onAuth();
      return;
    }
    setBusy(provider);
    try {
      const response = await api<{ url: string }>(`/auth/${provider}/start`);
      location.assign(response.url);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function upload(selected: File) {
    if (session?.demo) {
      onAuth();
      return;
    }
    setBusy("import");
    try {
      const data = new FormData();
      data.append("file", selected);
      const result = await api<{ imported: number; duplicates: number }>(
        "/api/ingest/file",
        { method: "POST", body: data },
      );
      notify(
        `Imported ${result.imported} measurements · ${result.duplicates} duplicates skipped.`,
      );
      onChange();
      reload();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function broadcast() {
    if (session?.demo) {
      onAuth();
      return;
    }
    if (broadcasting) {
      bleDevice.current?.gatt?.disconnect();
      setBroadcasting(false);
      return;
    }
    // Web Bluetooth is feature-detected. iPhone Safari does not expose this browser interface.
    const bluetooth = (
      navigator as Navigator & {
        bluetooth?: { requestDevice: (options: unknown) => Promise<any> };
      }
    ).bluetooth;
    if (!bluetooth) {
      notify(
        "Direct Bluetooth is unavailable in this browser. Use a supported desktop Chromium browser with your watch in heart-rate broadcast mode, or import a Garmin FIT activity.",
      );
      return;
    }
    try {
      const device = await bluetooth.requestDevice({
        filters: [{ services: ["heart_rate"] }],
      });
      bleDevice.current = device;
      const server = await device.gatt.connect();
      const service = await server.getPrimaryService("heart_rate");
      const characteristic = await service.getCharacteristic(
        "heart_rate_measurement",
      );
      let inFlight = false;
      characteristic.addEventListener(
        "characteristicvaluechanged",
        async (e: any) => {
          if (inFlight) return;
          inFlight = true;
          try {
            const view: DataView = e.target.value;
            const hr =
              view.getUint8(0) & 1 ? view.getUint16(1, true) : view.getUint8(1);
            await post("/api/ingest/bluetooth", {
              heart_rate_bpm: hr,
              event_time: new Date().toISOString(),
            });
          } catch (err) {
            notify((err as Error).message);
          } finally {
            inFlight = false;
          }
        },
      );
      await characteristic.startNotifications();
      setBroadcasting(true);
      device.addEventListener("gattserverdisconnected", () => {
        setBroadcasting(false);
        notify(
          "Heart-rate broadcast disconnected. Your saved measurements remain available.",
        );
      });
      notify(
        "Heart-rate broadcast connected. Only measured heart rate is streamed; no HRV or sleep values are inferred.",
      );
    } catch (e) {
      notify((e as Error).message);
    }
  }
  async function toggleGarminInflux() {
    if (session?.demo) {
      onAuth();
      return;
    }
    setBusy("garmin-influx");
    try {
      if (
        influxSyncStatus.status === "live" ||
        influxSyncStatus.status === "starting"
      ) {
        await post("/api/connect/garmin-influx/live/stop");
        setInfluxSyncStatus({ status: "stopped" });
      } else {
        setInfluxSyncStatus({ status: "starting" });
        await post("/api/connect/garmin-influx/live/start");
        notify(
          "Pulling your history from InfluxDB, then staying connected for new data.",
        );
      }
      onChange();
      reload();
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function toggleBleBridge() {
    if (session?.demo) {
      onAuth();
      return;
    }
    setBusy("garmin-ble-bridge");
    try {
      if (
        bleBridgeStatus.status === "connected" ||
        bleBridgeStatus.status === "connecting"
      ) {
        await post("/api/connect/garmin-ble-bridge/stop");
        setBleBridgeStatus({ status: "stopped" });
      } else {
        await post("/api/connect/garmin-ble-bridge/start");
        setBleBridgeStatus({ status: "connecting" });
        notify(
          "Connecting to the local live BLE script (ble_hr_live.py on ws://localhost:8765)…",
        );
      }
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setBusy("");
    }
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    if (session?.demo) {
      onAuth();
      return;
    }
    try {
      await api("/api/profile", {
        method: "PUT",
        body: JSON.stringify(profile),
      });
      notify("Preferences saved. Your next plan will use these settings.");
      onChange();
    } catch (e) {
      notify((e as Error).message);
    }
  }
  return (
    <div className="connections-page">
      <div className="section-intro">
        <span className="eyebrow">YOUR CONNECTED WORLD</span>
        <h2>Bring the pieces together.</h2>
        <p>
          Your watch, your schedule, and a voice that makes your data easier to
          understand.
        </p>
      </div>
      <div className="connection-grid">
        {[
          {
            id: "garmin",
            name: "Garmin Connect",
            icon: Watch,
            text: "Sleep, activity, resting heart rate, and uploaded heart-rate samples. Cloud sync requires approved Garmin developer access.",
          },
          {
            id: "google-calendar",
            name: "Google Calendar",
            icon: CalendarDays,
            text: "Find free time and add your chosen recovery or workout session, with a calendar reminder.",
          },
          {
            id: "microsoft-calendar",
            name: "Outlook Calendar",
            icon: CalendarDays,
            text: "The same free-time check and event creation, for Outlook/Microsoft 365 calendars. Connect either this or Google -- both at once works too, and busy time from both is checked.",
          },
          {
            id: "fitbit",
            name: "Fitbit / Google Health",
            icon: Watch,
            text: "An additional wearable source using Google Health. Connect only if you have a compatible device.",
          },
        ].map((item) => {
          const source = sources?.sources.find((s) => s.provider === item.id);
          return (
            <section className="card connection-card" key={item.id}>
              <div className="connection-icon">
                <item.icon size={24} />
              </div>
              <div className="connection-heading">
                <h3>{item.name}</h3>
                <span
                  className={`status-pill ${source?.status === "connected" ? "good" : ""}`}
                >
                  {source?.status === "connected"
                    ? "Connected"
                    : source?.status === "reconnect"
                      ? "Reconnect needed"
                      : "Not connected"}
                </span>
              </div>
              <p>{item.text}</p>
              {source?.sync?.status === "error" && (
                <p className="error">
                  Sync failed: {source.sync.error}. Check your provider
                  connection.
                </p>
              )}
              <div className="connection-actions">
                <button
                  className="button"
                  disabled={busy === item.id}
                  onClick={() => connect(item.id)}
                >
                  {busy === item.id
                    ? "Opening…"
                    : source?.status === "connected"
                      ? "Reconnect"
                      : "Connect account"}
                  <ArrowUpRight size={15} />
                </button>
                {source?.status === "connected" && (
                  <button
                    className="icon-btn"
                    aria-label={`Disconnect ${item.name}`}
                    onClick={async () => {
                      try {
                        await api(`/auth/${item.id}`, { method: "DELETE" });
                        reload();
                        notify("Account disconnected.");
                      } catch (e) {
                        notify((e as Error).message);
                      }
                    }}
                  >
                    <LogOut size={16} />
                  </button>
                )}
              </div>
              {!source?.configured && (
                <small className="setup-note">
                  Server setup required · see the integration guide
                </small>
              )}
            </section>
          );
        })}
        <section className="card connection-card">
          <div className="connection-icon">
            <AudioLines size={24} />
          </div>
          <div className="connection-heading">
            <h3>ElevenLabs voice</h3>
            <span
              className={`status-pill ${sources?.elevenlabs.configured ? "good" : ""}`}
            >
              {sources?.elevenlabs.configured ? "Ready" : "Setup required"}
            </span>
          </div>
          <p>
            Your twin speaks its grounded answers with ElevenLabs. Only the
            response text is sent for speech generation.
          </p>
          <small className="setup-note">
            {sources?.elevenlabs.configured
              ? "Ask your twin a question to hear its answer. Saved conversations can be replayed with Listen."
              : "Add ELEVENLABS_API_KEY to the server .env, then restart."}
          </small>
        </section>
      </div>
      <div className="two-col">
        <section className="card import-card">
          <span className="eyebrow">START WITH YOUR WATCH</span>
          <h3>Your Garmin, four more ways.</h3>
          <p>
            Import an original Garmin activity FIT file or a supported JSON
            export. Recorded data follows the same model and avatar pipeline.
          </p>
          <input
            ref={file}
            type="file"
            accept=".fit,.json"
            hidden
            onChange={(e) => {
              if (e.target.files?.[0]) upload(e.target.files[0]);
              e.target.value = "";
            }}
          />
          <button
            className="button primary"
            onClick={() => (session?.demo ? onAuth() : file.current?.click())}
            disabled={busy === "import"}
          >
            <Upload size={16} />
            {busy === "import"
              ? "Importing measurements…"
              : "Import Garmin data"}
          </button>
          <div className="connection-divider" />
          <h4>Direct heart-rate broadcast</h4>
          <p>
            On supported watches, enable Broadcast Heart Rate. Connect from a
            browser that supports Bluetooth. Keep this screen open while
            broadcasting.
          </p>
          <button className="button" onClick={broadcast}>
            <Bluetooth size={16} />
            {broadcasting
              ? "Disconnect broadcast"
              : "Connect heart-rate broadcast"}
          </button>
          <div className="connection-divider" />
          <h4>Local Garmin dashboard (InfluxDB)</h4>
          <p>
            Already running the standalone garmin viz dashboard on this
            machine? Pull its history, then stay connected -- new points it
            writes keep flowing into this twin as they land, not just once.
          </p>
          <button
            className="button"
            onClick={toggleGarminInflux}
            disabled={busy === "garmin-influx"}
          >
            <RefreshCw size={16} />
            {influxSyncStatus.status === "live"
              ? "Disconnect (stop live sync)"
              : influxSyncStatus.status === "starting"
                ? "Connecting…"
                : "Connect to Garmin (sync + stay live)"}
          </button>
          {influxSyncStatus.status === "live" && (
            <small className="setup-note">
              Live · watching for new InfluxDB data
              {influxSyncStatus.last_frame_at
                ? ` · last point ${new Date(influxSyncStatus.last_frame_at).toLocaleTimeString()}`
                : ""}
            </small>
          )}
          {influxSyncStatus.status === "error" && (
            <p className="error">{influxSyncStatus.detail}</p>
          )}
          <h4>Live from the terminal script</h4>
          <p>
            Bridges the already-running <code>ble_hr_live.py</code> BLE
            script (heart-rate broadcast, no browser Bluetooth required)
            into this twin in real time, heartbeat by heartbeat.
          </p>
          <button
            className="button"
            onClick={toggleBleBridge}
            disabled={busy === "garmin-ble-bridge"}
          >
            <Radio size={16} />
            {bleBridgeStatus.status === "connected"
              ? "Disconnect live bridge"
              : bleBridgeStatus.status === "connecting"
                ? "Connecting…"
                : "Go live"}
          </button>
          {bleBridgeStatus.status === "error" && (
            <p className="error">{bleBridgeStatus.detail}</p>
          )}
        </section>
        <section className="card">
          <div className="card-heading">
            <h3>Your daily rhythm</h3>
            <RefreshCw size={16} />
          </div>
          <form className="preferences" onSubmit={save}>
            <label>
              Timezone
              <input
                value={profile.timezone}
                onChange={(e) =>
                  setProfile({ ...profile, timezone: e.target.value })
                }
              />
            </label>
            <div className="form-row">
              <label>
                Usual bedtime
                <input
                  type="time"
                  value={profile.bedtime}
                  onChange={(e) =>
                    setProfile({ ...profile, bedtime: e.target.value })
                  }
                />
              </label>
              <label>
                Sleep target · minutes
                <input
                  type="number"
                  min={360}
                  max={600}
                  value={profile.target_sleep}
                  onChange={(e) =>
                    setProfile({
                      ...profile,
                      target_sleep: Number(e.target.value),
                    })
                  }
                />
              </label>
            </div>
            <label>
              Workout length · minutes
              <input
                type="number"
                min={10}
                max={120}
                value={profile.workout_minutes}
                onChange={(e) =>
                  setProfile({
                    ...profile,
                    workout_minutes: Number(e.target.value),
                  })
                }
              />
            </label>
            <label className="check-label">
              <input
                type="checkbox"
                checked={profile.naps_enabled}
                onChange={(e) =>
                  setProfile({ ...profile, naps_enabled: e.target.checked })
                }
              />
              Include nap suggestions
            </label>
            <button className="button" type="submit">
              <Check size={15} />
              Save preferences
            </button>
          </form>
        </section>
      </div>
      {!session?.demo && (
        <section className="card privacy-card">
          <div>
            <h3>Your data belongs to you.</h3>
            <p>
              Measurements are retained for {session?.retention_days ?? 90}{" "}
              days. Export your history or permanently delete your account.
            </p>
          </div>
          <a className="button" href="/api/data/export" download>
            <Download size={16} />
            Export data
          </a>
          <button className="button danger" onClick={() => setDeleting(true)}>
            <Trash2 size={15} />
            Delete account
          </button>
        </section>
      )}
      {deleting && (
        <div className="modal-backdrop">
          <section
            className="auth-modal"
            role="dialog"
            aria-modal="true"
            aria-label="Delete your account"
          >
            <h2>Delete your BioTwin data?</h2>
            <p>
              This permanently deletes your account, measurements, tokens, and
              computed history. Existing calendar events stay in Google
              Calendar.
            </p>
            <div className="form-row">
              <button className="button" onClick={() => setDeleting(false)}>
                Keep my account
              </button>
              <button
                className="button danger"
                onClick={async () => {
                  try {
                    const result = await api<{
                      provider_revocation_failed: string[];
                    }>("/api/data", { method: "DELETE" });
                    setDeleting(false);
                    onChange();
                    notify(
                      result.provider_revocation_failed.length
                        ? "Local data deleted. Revoke BioTwin access in your provider account settings as well."
                        : "Account and data deleted.",
                    );
                  } catch (e) {
                    notify((e as Error).message);
                  }
                }}
              >
                Delete permanently
              </button>
            </div>
          </section>
        </div>
      )}
    </div>
  );
}
