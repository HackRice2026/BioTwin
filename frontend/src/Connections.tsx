import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import {
  Watch,
  Link2,
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
import type { TwinState } from "./contracts";
import WatchConnection from "./WatchConnection";

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
  state,
}: {
  session: Session | null;
  onAuth: () => void;
  onChange: () => void;
  notify: (s: string) => void;
  state?: TwinState;
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
  useEffect(() => {
    if (session?.user.profile) setProfile(session.user.profile);
  }, [session?.user.id]);
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
  }, [session?.user.id]);
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
  async function seedCalendar(id: string) {
    setBusy(`seed:${id}`);
    try {
      const result = await post<{
        seeded: boolean;
        created: number;
        reason?: string;
      }>("/api/calendar/seed");
      notify(
        result.seeded
          ? `Added ${result.created} sample events for the coming week.`
          : (result.reason ?? "Your calendar already has events coming up."),
      );
      reload();
      if (result.seeded) onChange();
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
        notify("Connecting to your live watch companion…");
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
      <div className="connections-summary glass">
        <span className="connection-icon">
          <Link2 size={25} />
        </span>
        <div>
          <span className="eyebrow">BETTER TOGETHER</span>
          <h2>A home for your everyday signals.</h2>
          <p>
            Bring your watch and calendar together. Choose what you connect.
          </p>
        </div>
      </div>
      <div className="section-label">
        <h2>Connected accounts</h2>
        <span className="fine-print">Your data stays yours</span>
      </div>
      <div className="connection-grid">
        {[
          {
            id: "garmin",
            name: "Garmin Connect",
            icon: Watch,
            text: "Your sleep, activity and heart-rate history, directly from your watch account.",
          },
          {
            id: "google-calendar",
            name: "Google Calendar",
            icon: CalendarDays,
            text: "Find a free window and add the sessions you choose, with reminders.",
          },
          {
            id: "microsoft-calendar",
            name: "Outlook Calendar",
            icon: CalendarDays,
            text: "Fit your recovery around work and life. Busy time from both calendars is respected.",
          },
          {
            id: "fitbit",
            name: "Fitbit / Google Health",
            icon: Watch,
            text: "Add another view of your day from a compatible Fitbit wearable.",
          },
        ].map((item) => {
          const source = sources?.sources.find((s) => s.provider === item.id);
          return (
            <section key={item.id} className="connection-card glass">
              <div className="provider-top">
                <span className="connection-icon">
                  <item.icon size={23} />
                </span>
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
              <h3>{item.name}</h3>
              <p>{item.text}</p>
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
                        onChange();
                        notify("Account disconnected.");
                      } catch {
                        notify(
                          "Couldn't disconnect this account. Please try again.",
                        );
                      }
                    }}
                  >
                    <LogOut size={16} />
                  </button>
                )}
              </div>
              {source?.sync?.status === "error" && (
                <p className="error">
                  Sync couldn't finish. Reconnect your account and try again.
                </p>
              )}
              {!source?.configured && (
                <small className="setup-note">
                  This connection isn't available on this instance yet.
                </small>
              )}
              {item.id.includes("calendar") &&
                source?.status === "connected" && (
                  <details className="disclosure">
                    <summary>Try a sample schedule</summary>
                    <p>
                      Add sample events only if your coming week is completely
                      empty.
                    </p>
                    <button
                      className="text-button"
                      disabled={busy === `seed:${item.id}`}
                      onClick={() => seedCalendar(item.id)}
                    >
                      {busy === `seed:${item.id}`
                        ? "Checking…"
                        : "Add a sample week"}
                    </button>
                  </details>
                )}
            </section>
          );
        })}
      </div>
      <div className="section-label">
        <h2>Your watch, your way</h2>
      </div>
      <WatchConnection
        personal={!!session && !session.demo}
        setup
        onAuth={onAuth}
        state={state}
      />
      <section className="watch-methods glass">
        <div className="watch-method">
          <span className="connection-icon">
            <Upload size={21} />
          </span>
          <div>
            <h3>Bring your history</h3>
            <p>
              Import an original Garmin FIT activity or a supported JSON export.
            </p>
          </div>
          <input
            ref={file}
            type="file"
            accept=".fit,.json"
            hidden
            onChange={(e) => {
              if (e.target.files?.[0]) void upload(e.target.files[0]);
              e.target.value = "";
            }}
          />
          <button
            className="button"
            disabled={busy === "import"}
            onClick={() => (session?.demo ? onAuth() : file.current?.click())}
          >
            {busy === "import" ? "Importing…" : "Import Garmin data"}
            <Upload size={14} />
          </button>
        </div>
        <div className="watch-method">
          <span className="connection-icon">
            <Bluetooth size={21} />
          </span>
          <div>
            <h3>Heart rate, as it happens</h3>
            <p>
              Enable heart-rate broadcast on your watch, then pair it with a
              supported browser.
            </p>
          </div>
          <button className="button" onClick={broadcast}>
            {broadcasting
              ? "Disconnect broadcast"
              : "Connect heart-rate broadcast"}
          </button>
        </div>
        <div className="watch-method">
          <span className="connection-icon">
            <RefreshCw size={21} />
          </span>
          <div>
            <h3>Garmin companion sync</h3>
            <p>
              Bring in your locally synced history and keep receiving new
              measurements.
            </p>
            {influxSyncStatus.status === "live" && (
              <span className="status-pill good">
                Syncing
                {influxSyncStatus.last_frame_at
                  ? ` · ${new Date(influxSyncStatus.last_frame_at).toLocaleTimeString()}`
                  : ""}
              </span>
            )}
            {influxSyncStatus.status === "error" && (
              <p className="error">
                The companion couldn't be reached. Check that it's running.
              </p>
            )}
          </div>
          <button
            className="button"
            disabled={busy === "garmin-influx"}
            onClick={toggleGarminInflux}
          >
            {influxSyncStatus.status === "live"
              ? "Stop sync"
              : influxSyncStatus.status === "starting"
                ? "Connecting…"
                : "Connect companion"}
          </button>
        </div>
        <div className="watch-method">
          <span className="connection-icon">
            <Radio size={21} />
          </span>
          <div>
            <h3>Live watch companion</h3>
            <p>
              Use your computer's live watch connection, including from a phone
              browser.
            </p>
            {bleBridgeStatus.status === "error" && (
              <p className="error">
                The live companion couldn't be reached. Check your watch
                connection.
              </p>
            )}
          </div>
          <button
            className="button"
            disabled={busy === "garmin-ble-bridge"}
            onClick={toggleBleBridge}
          >
            {bleBridgeStatus.status === "connected"
              ? "Disconnect live bridge"
              : bleBridgeStatus.status === "connecting"
                ? "Connecting…"
                : "Go live"}
          </button>
        </div>
      </section>
      <div className="two-col">
        <section className="glass">
          <div className="panel-title">
            <div>
              <h2>Your daily rhythm</h2>
              <p>Make your next plan feel like you.</p>
            </div>
            <CalendarDays size={20} className="green" />
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
        <section className="voice-connection glass">
          <span className="connection-icon">
            <AudioLines size={24} />
          </span>
          <span
            className={`status-pill ${sources?.elevenlabs.configured ? "good" : ""}`}
          >
            {sources?.elevenlabs.configured
              ? "Ready to talk"
              : "Text available"}
          </span>
          <h2>
            A familiar voice.
            <br />A little more clarity.
          </h2>
          <p>
            Your twin turns your measurements into a conversation. Its voice is
            powered by ElevenLabs.
          </p>
          <p className="fine-print">
            Only the answer text is sent to create speech. Your questions and
            answers are saved in your private conversation history.
          </p>
        </section>
      </div>
      {session && !session.demo && (
        <section className="privacy-card glass">
          <div>
            <h3>Yours to keep. Yours to control.</h3>
            <p>
              Measurements are kept for {session.retention_days} days. Export
              your history whenever you like.
            </p>
          </div>
          <a className="button" href="/api/data/export" download>
            <Download size={15} />
            Export data
          </a>
          <button className="button danger" onClick={() => setDeleting(true)}>
            <Trash2 size={14} />
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
              This permanently deletes your account, measurements, connections
              and conversations. Existing calendar events stay in your calendar.
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
                        ? "Local data deleted. Revoke BioTwin in your provider account settings as well."
                        : "Account and data deleted.",
                    );
                  } catch {
                    notify(
                      "Your account couldn't be deleted. Please try again.",
                    );
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
