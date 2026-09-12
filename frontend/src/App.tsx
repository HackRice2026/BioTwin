import { useEffect, useRef, useState } from "react";
import type { FormEvent, ReactNode } from "react";
import {
  Activity,
  ArrowRight,
  ArrowUpRight,
  AudioLines,
  Battery,
  CalendarDays,
  Check,
  ChevronRight,
  CloudOff,
  FlaskConical,
  Heart,
  HelpCircle,
  LayoutDashboard,
  Leaf,
  Link2,
  LoaderCircle,
  Moon,
  MoveUpRight,
  Pause,
  RefreshCw,
  Send,
  Settings2,
  ShieldCheck,
  Sparkles,
  Sun,
  Volume2,
  Wind,
  X,
  Footprints,
  Mic,
} from "lucide-react";
import Avatar from "./Avatar";
import Connections, { AuthModal } from "./Connections";
import { useTwin } from "./transport";
import { api, post, humanize, value } from "./api";
import type { Session, MetricPoint, SleepPoint } from "./api";
import type {
  DailyPlan,
  Readiness,
  RecoveryPrediction,
  SimulationOverlay,
  TwinState,
  DayOutlook,
} from "./contracts";
import {
  ProvenanceChip,
  Sparkline,
  RecoveryChart,
  SignalChart,
  SleepChart,
  ReadinessChart,
  OutlookChart,
} from "./Charts";

type Page =
  | "Overview"
  | "Signals"
  | "Daily plan"
  | "What-if lab"
  | "Connections";
const navigation: { name: Page; icon: typeof Activity }[] = [
  { name: "Overview", icon: LayoutDashboard },
  { name: "Signals", icon: Activity },
  { name: "Daily plan", icon: CalendarDays },
  { name: "What-if lab", icon: FlaskConical },
  { name: "Connections", icon: Link2 },
];
const emptySeries: Record<string, MetricPoint[]> = {
  heart_rate_bpm: [],
  hrv_rmssd_ms: [],
  resting_hr_bpm: [],
  respiration_brpm: [],
  spo2_pct: [],
  steps: [],
};
type Reply = {
  answer: string;
  mode: string;
  reply_id?: string;
  voice_configured?: boolean;
};
type Message = { role: "user" | "twin"; text: string; reply?: Reply };

function Card({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <section className={`card ${className}`}>{children}</section>;
}
function MetricCard({
  name,
  reading,
  unit,
  detail,
  icon: Icon,
  data,
  source,
}: {
  name: string;
  reading: number | null | undefined;
  unit: string;
  detail: string;
  icon: typeof Heart;
  data: MetricPoint[];
  source?: string;
}) {
  return (
    <Card className="metric-card">
      <div className="metric-name">
        <Icon size={16} />
        <span>{name}</span>
        <ProvenanceChip source={source} />
      </div>
      <div className="metric-value">
        {value(reading, 1)}
        <span>{unit}</span>
      </div>
      <div className="metric-footer">
        <span>{detail}</span>
        <div className="sparkline">
          <Sparkline data={data} />
        </div>
      </div>
    </Card>
  );
}
function ReadinessPanel({
  state,
  onSignals,
}: {
  state: TwinState;
  onSignals: () => void;
}) {
  const ready = state.readiness,
    score = ready.score;
  return (
    <Card className="readiness-card">
      <div className="card-heading">
        <div>
          <span className="eyebrow">A MOMENT FOR YOU</span>
          <h3>Today's readiness</h3>
        </div>
        <button
          className="icon-btn"
          aria-label="Explore readiness signals"
          onClick={onSignals}
        >
          <ArrowUpRight size={18} />
        </button>
      </div>
      <div className="readiness-content">
        <div
          className="score-ring"
          style={{
            background: `conic-gradient(#437e61 ${(score ?? 0) * 3.6}deg,#edf0e7 0deg)`,
          }}
        >
          <div>
            <strong>{value(score)}</strong>
            <span>OUT OF 100</span>
          </div>
        </div>
        <div className="readiness-copy">
          <span className="state-tag">
            <Leaf size={13} />
            {score == null ? "Calibrating" : humanize(ready.state)}
          </span>
          <h4>
            {score == null
              ? "Let’s get to know you."
              : score >= 65
                ? "Room to move forward."
                : score >= 45
                  ? "Find your own rhythm."
                  : "Make space to recharge."}
          </h4>
          <p>
            {score == null
              ? "Connect your Garmin or import a recorded activity to begin."
              : "An estimate based on your sleep, heart-rate variability, and resting pattern."}
          </p>
          <span className="confidence">
            Confidence <b>{value(ready.confidence * 100)}%</b>
          </span>
        </div>
      </div>
      <div className="calibration">
        <div>
          <span>
            <span className="calibration-dot" />
            Learning your pattern
          </span>
          <b>
            {value(state.baseline_summary.shrinkage_weight * 100)}% personal
          </b>
        </div>
        <div className="progress-track">
          <span
            style={{
              width: `${state.baseline_summary.shrinkage_weight * 100}%`,
            }}
          />
        </div>
      </div>
    </Card>
  );
}

export default function App() {
  const [page, setPage] = useState<Page>("Overview"),
    [accountKey, setAccountKey] = useState(0),
    [session, setSession] = useState<Session | null>(null);
  const { state, live, status, bundle, error } = useTwin(accountKey);
  const overlay = useRef<SimulationOverlay | null>(null);
  const [simulation, setSimulation] = useState<SimulationOverlay | null>(null),
    [scenarioBusy, setScenarioBusy] = useState("");
  const [metrics, setMetrics] = useState(emptySeries),
    [sleep, setSleep] = useState<SleepPoint[]>([]),
    [history, setHistory] = useState<Readiness[]>([]),
    [predictions, setPredictions] = useState<RecoveryPrediction[]>([]),
    [plan, setPlan] = useState<DailyPlan | null>(null),
    [outlook, setOutlook] = useState<DayOutlook | null>(null);
  const [days, setDays] = useState(7),
    [toast, setToast] = useState(""),
    [auth, setAuth] = useState(false),
    [chat, setChat] = useState(false),
    [messages, setMessages] = useState<Message[]>([]),
    [question, setQuestion] = useState(""),
    [asking, setAsking] = useState(false),
    [speaking, setSpeaking] = useState(false),
    [reminder, setReminder] = useState(10),
    [adding, setAdding] = useState(""),
    [added, setAdded] = useState<string[]>([]);
  const [reduced, setReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const [ops, setOps] = useState<Record<string, unknown> | null>(null),
    [showOps, setShowOps] = useState(false),
    [loadingPlan, setLoadingPlan] = useState(false);
  const audio = useRef<HTMLAudioElement | null>(null),
    messagesEnd = useRef<HTMLDivElement>(null);
  const notify = (s: string) => setToast(s);
  const changed = () => {
    audio.current?.pause();
    setSpeaking(false);
    setSession(null);
    setMetrics(emptySeries);
    setSleep([]);
    setHistory([]);
    setPredictions([]);
    setPlan(null);
    setOutlook(null);
    setAccountKey((k) => k + 1);
    overlay.current = null;
    setSimulation(null);
    setMessages([]);
    setAdded([]);
  };
  useEffect(() => {
    api<Session>("/api/session")
      .then(setSession)
      .catch(() => setSession(null));
  }, [accountKey, status]);
  useEffect(() => {
    if (!toast) return;
    const timer = setTimeout(() => setToast(""), 8000);
    return () => clearTimeout(timer);
  }, [toast]);
  useEffect(() => {
    messagesEnd.current?.scrollIntoView({
      behavior: reduced ? "instant" : "smooth",
    });
  }, [messages, chat, reduced]);
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
    let cancelled = false;
    const load = async () => {
      const results = await Promise.allSettled([
        ...Object.keys(emptySeries).map((m) =>
          api<{ series: MetricPoint[] }>(
            `/api/metrics?metric=${m}&days=${days}`,
          ),
        ),
        api<{ series: SleepPoint[] }>(`/api/metrics?metric=sleep&days=${days}`),
        api<Readiness[]>("/api/readiness/history"),
        api<RecoveryPrediction[]>("/api/predictions"),
        api<DailyPlan>("/api/plan/today"),
        api<DayOutlook>("/api/outlook"),
      ]);
      if (cancelled) return;
      const next = { ...emptySeries };
      Object.keys(emptySeries).forEach((m, i) => {
        const result = results[i];
        if (result.status === "fulfilled")
          next[m] = (result.value as { series: MetricPoint[] }).series;
      });
      setMetrics(next);
      const [s, h, p, pl, out] = results.slice(6);
      if (s.status === "fulfilled")
        setSleep((s.value as { series: SleepPoint[] }).series);
      if (h.status === "fulfilled") setHistory(h.value as Readiness[]);
      if (p.status === "fulfilled")
        setPredictions(p.value as RecoveryPrediction[]);
      if (pl.status === "fulfilled") setPlan(pl.value as DailyPlan);
      if (out.status === "fulfilled") setOutlook(out.value as DayOutlook);
      const failure = results.find((r) => r.status === "rejected");
      if (failure?.status === "rejected") notify(failure.reason.message);
    };
    load();
    const timer = setInterval(load, 60000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [status, bundle, days, accountKey]);
  useEffect(
    () => () => {
      audio.current?.pause();
    },
    [],
  );
  function navigate(next: Page) {
    setPage(next);
    if (next !== "What-if lab") {
      overlay.current = null;
      setSimulation(null);
    }
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  async function simulate(scenario: string) {
    if (status === "offline" && bundle?.simulations[scenario]) {
      const result=bundle.simulations[scenario];
      overlay.current=result;
      setSimulation(result);
      return;
    }
    if (status !== "online") {
      notify(
        "The selected scenario is not available in this replay. Reconnect to compute it.",
      );
      return;
    }
    setScenarioBusy(scenario);
    try {
      const result = await post<SimulationOverlay>("/api/simulate", {
        scenario,
      });
      overlay.current = result;
      setSimulation(result);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setScenarioBusy("");
    }
  }
  async function refreshPlan() {
    setLoadingPlan(true);
    try {
      setPlan(await post<DailyPlan>("/api/plan/refresh"));
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setLoadingPlan(false);
    }
  }
  async function addEvent(id: string) {
    if (session?.demo || !session) {
      setAuth(true);
      return;
    }
    setAdding(id);
    try {
      await post("/api/calendar/events", {
        proposal_id: id,
        reminder_minutes: reminder,
      });
      setAdded((a) => [...a, id]);
      notify(`Added to Google Calendar with a ${reminder}-minute reminder.`);
    } catch (e) {
      notify((e as Error).message);
    } finally {
      setAdding("");
    }
  }
  async function ask(text: string) {
    if (!text.trim() || asking) return;
    setQuestion("");
    setMessages((m) => [...m, { role: "user", text }]);
    setAsking(true);
    try {
      let reply: Reply;
      if (status === "offline" && bundle) {
        const key = /recover|predict/i.test(text)
          ? "recovery"
          : /sleep/i.test(text)
            ? "sleep"
            : /plan|nap|workout/i.test(text)
              ? "plan"
              : "readiness";
        reply = {
          answer: `Offline example: ${bundle.answers[key] ?? "Reconnect to ask about your personal measurements."}`,
          mode: "offline",
        };
      } else reply = await post<Reply>("/api/twin/ask", { question: text });
      setMessages((m) => [...m, { role: "twin", text: reply.answer, reply }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "twin", text: (e as Error).message }]);
    } finally {
      setAsking(false);
    }
  }
  function speak(reply: Reply) {
    if (!reply.voice_configured || !reply.reply_id) {
      notify(
        "ElevenLabs voice needs an API key on the server. The text answer is available now.",
      );
      return;
    }
    audio.current?.pause();
    const player = new Audio(`/api/voice/${reply.reply_id}`);
    audio.current = player;
    player.onplaying = () => setSpeaking(true);
    player.onended = () => setSpeaking(false);
    player.onerror = () => {
      setSpeaking(false);
      notify(
        "Speech could not play. Check the ElevenLabs connection, or ask again if this response has expired.",
      );
    };
    player.play().catch(() => {
      setSpeaking(false);
      notify("Audio playback was blocked. Use Listen again to start playback.");
    });
  }
  function microphone() {
    const Recognition =
      (
        window as Window & {
          SpeechRecognition?: any;
          webkitSpeechRecognition?: any;
        }
      ).SpeechRecognition ||
      (window as Window & { webkitSpeechRecognition?: any })
        .webkitSpeechRecognition;
    if (!Recognition) {
      notify(
        "Microphone transcription is unavailable in this browser. Type your question below.",
      );
      return;
    }
    const recognition = new Recognition();
    recognition.lang = "en-US";
    recognition.onresult = (e: any) => setQuestion(e.results[0][0].transcript);
    recognition.onerror = () =>
      notify("Microphone input was unavailable. You can type your question.");
    recognition.start();
  }
  const isDemo = status === "offline" || session?.demo;
  const prediction = state?.prediction?.curve.length
    ? state.prediction
    : predictions[0];
  const quality = state?.quality ?? {};
  const source = (metric: string) => quality[metric]?.provenance;
  const dateLabel = new Date().toLocaleDateString(undefined, {
    weekday: "short",
    month: "short",
    day: "numeric",
  });
  const latest = state?.latest;
  const title: Record<Page, string> = {
    Overview: "Your day, understood.",
    Signals: "Listen to your signals.",
    "Daily plan": "Make room for yourself.",
    "What-if lab": "Explore a different rhythm.",
    Connections: "A more connected you.",
  };
  const planContent = (
    <>
      <div className="card-heading">
        <div>
          <span className="eyebrow">SMALL MOMENTS. MORE BALANCE.</span>
          <h3>Your daily plan</h3>
        </div>
        <button
          className="icon-btn"
          aria-label="Refresh daily plan"
          onClick={refreshPlan}
          disabled={loadingPlan}
        >
          <RefreshCw size={17} className={loadingPlan ? "spin" : ""} />
        </button>
      </div>
      <div className="plan-status">
        <CalendarDays size={13} />
        {plan?.calendar_status === "connected"
          ? "Google Calendar connected"
          : plan?.calendar_status === "demo"
            ? "Example schedule · synthetic demo"
            : "Connect Google Calendar for verified availability"}
      </div>
      {plan?.proposals.length ? (
        <div className="plan-list">
          {plan.proposals.map((p) => (
            <div className="plan-item" key={p.id}>
              <span className={`plan-icon ${p.kind}`}>
                {p.kind === "nap" ? (
                  <Moon size={19} />
                ) : (
                  <Footprints size={19} />
                )}
              </span>
              <div className="plan-description">
                <span className="plan-time">
                  {new Date(p.start).toLocaleTimeString(undefined, {
                    hour: "numeric",
                    minute: "2-digit",
                    timeZone: plan.timezone,
                  })}{" "}
                  —{" "}
                  {new Date(p.end).toLocaleTimeString(undefined, {
                    hour: "numeric",
                    minute: "2-digit",
                    timeZone: plan.timezone,
                  })}
                </span>
                <h4>{p.title}</h4>
                <p>{p.reason}</p>
              </div>
              <button
                className={`add-calendar ${added.includes(p.id) ? "added" : ""}`}
                disabled={adding === p.id || added.includes(p.id)}
                aria-label={`Add ${p.title} to calendar`}
                onClick={() => addEvent(p.id)}
              >
                {added.includes(p.id) ? (
                  <Check size={16} />
                ) : adding === p.id ? (
                  <LoaderCircle size={16} className="spin" />
                ) : (
                  <ArrowUpRight size={18} />
                )}
              </button>
            </div>
          ))}
        </div>
      ) : (
        <div className="plan-empty">
          <CalendarDays size={25} />
          <p>{plan?.explanation ?? "Building your plan…"}</p>
          <button
            className="text-button"
            onClick={() => navigate("Connections")}
          >
            Connect your calendar <ArrowRight size={14} />
          </button>
        </div>
      )}
      <div className="plan-foot">
        <span>Reminder before each added event</span>
        <select
          aria-label="Calendar reminder"
          value={reminder}
          onChange={(e) => setReminder(Number(e.target.value))}
        >
          <option value={5}>5 min</option>
          <option value={10}>10 min</option>
          <option value={15}>15 min</option>
          <option value={30}>30 min</option>
        </select>
      </div>
    </>
  );
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          href="#"
          className="brand"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <img src="/icon.svg" alt="" />
          <span>
            Bio<span>Twin</span>
          </span>
        </a>
        <span className="sidebar-label">YOUR PERSONAL HEALTH SPACE</span>
        <nav>
          {navigation.map((item) => (
            <button
              key={item.name}
              className={page === item.name ? "active" : ""}
              onClick={() => navigate(item.name)}
            >
              <item.icon size={19} />
              <span>{item.name}</span>
              {item.name === "What-if lab" && (
                <span className="nav-new">LAB</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-twin">
          <div className="twin-orbit">
            <Sparkles size={21} />
          </div>
          <h4>
            A little self-awareness
            <br />
            goes a long way.
          </h4>
          <p>
            Get to know the patterns
            <br />
            that make you, you.
          </p>
          <button onClick={() => setChat(true)}>
            Talk to your twin <ArrowUpRight size={15} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <button
            className="sidebar-secondary"
            onClick={() => {
              setShowOps(true);
              api<Record<string, unknown>>("/ops/status")
                .then(setOps)
                .catch((e) => notify(e.message));
            }}
          >
            <ShieldCheck size={17} /> System status
          </button>
          <button
            className="account"
            onClick={() =>
              session && !session.demo ? navigate("Connections") : setAuth(true)
            }
          >
            <span className="user-avatar">
              {isDemo ? "A" : (session?.user.name?.[0] ?? "Y")}
            </span>
            <span>
              <b>
                {isDemo
                  ? "Explore the demo"
                  : (session?.user.name ?? "Your account")}
              </b>
              <small>{isDemo ? "Make it yours →" : "Personal workspace"}</small>
            </span>
            <Settings2 size={16} />
          </button>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Your workspace <ChevronRight size={13} />
            <b>{page}</b>
          </div>
          <div className="topbar-actions">
            <span
              className={`connection-status ${status === "offline" ? "offline" : ""}`}
            >
              <i />
              {status === "offline"
                ? "Offline replay"
                : isDemo
                  ? "Synthetic demo"
                  : status === "online"
                    ? "Twin connected"
                    : "Connecting"}
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-btn"
              aria-label="About BioTwin"
              onClick={() =>
                notify(
                  "BioTwin explains wearable measurements and experimental recovery estimates. It is built for adult wellness and does not assess medical conditions.",
                )
              }
            >
              <HelpCircle size={18} />
            </button>
            {session && !session.demo && (
              <button
                className="text-button"
                onClick={async () => {
                  await post("/auth/session/logout");
                  changed();
                }}
              >
                Sign out
              </button>
            )}
          </div>
        </header>
        <main>
          <div className="page-heading">
            <div>
              <div className="greeting">
                <Sun size={14} />
                {isDemo
                  ? "A WINDOW INTO YOUR WELLBEING"
                  : "WELCOME TO YOUR PERSONAL TWIN"}
              </div>
              <h1>{title[page]}</h1>
              <p>Your recovery, your rhythm, your next step.</p>
            </div>
            <div className="heading-right">
              <span className="date-pill">
                <CalendarDays size={15} />
                {dateLabel}
              </span>
              <button
                className="button primary chat-launch"
                onClick={() => setChat(true)}
              >
                <AudioLines size={17} />
                Talk to my twin
              </button>
            </div>
          </div>
          {status === "offline" && (
            <div className="offline-banner" role="status">
              <CloudOff size={18} />
              <div>
                <b>OFFLINE / REPLAY</b>
                <span>
                  You’re viewing a bundled synthetic example. Your personal data
                  is not being updated.
                </span>
              </div>
              <button className="text-button" onClick={changed}>
                Reconnect <RefreshCw size={13} />
              </button>
            </div>
          )}
          {error && <div className="notice error">{error}</div>}
          {isDemo && status !== "offline" && (
            <div className="demo-banner">
              <span>
                <i />A working preview with synthetic wearable data.
              </span>
              <button onClick={() => setAuth(true)}>
                Connect your own story <ArrowRight size={14} />
              </button>
            </div>
          )}
          {!state && (
            <div className="loading-screen">
              <LoaderCircle className="spin" />
              <p>Connecting the pieces of your twin…</p>
            </div>
          )}
          {state && page === "Overview" && (
            <>
              <div className="metrics-grid">
                <MetricCard
                  name="Heart rate"
                  reading={latest?.heart_rate_bpm}
                  unit="bpm"
                  icon={Heart}
                  detail={
                    quality.heart_rate_bpm
                      ? `Recorded ${new Date(quality.heart_rate_bpm.event_time).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" })}`
                      : "Awaiting a measurement"
                  }
                  data={metrics.heart_rate_bpm ?? []}
                  source={source("heart_rate_bpm")}
                />
                <MetricCard
                  name="Heart-rate variability"
                  reading={latest?.hrv_rmssd_ms}
                  unit="ms"
                  icon={Activity}
                  detail="RMSSD · latest recorded"
                  data={metrics.hrv_rmssd_ms ?? []}
                  source={source("hrv_rmssd_ms")}
                />
                <MetricCard
                  name="Last night's sleep"
                  reading={latest?.sleep?.total_minutes}
                  unit="min"
                  icon={Moon}
                  detail="Time asleep · latest session"
                  data={sleep.map((s) => ({
                    time: s.time,
                    value: s.value.total_minutes,
                    provenance: s.provenance,
                    confidence: 1,
                  }))}
                  source={source("sleep")}
                />
                <MetricCard
                  name="Resting heart rate"
                  reading={latest?.resting_hr_bpm}
                  unit="bpm"
                  icon={Leaf}
                  detail="Your daily resting pattern"
                  data={metrics.resting_hr_bpm ?? []}
                  source={source("resting_hr_bpm")}
                />
              </div>
              <div className="hero-grid">
                <Avatar
                  live={live}
                  overlay={overlay}
                  state={state}
                  reduced={reduced}
                  speaking={speaking}
                />
                <div className="hero-panels">
                  <ReadinessPanel
                    state={state}
                    onSignals={() => navigate("Signals")}
                  />
                  <Card className="recovery-card">
                    <div className="card-heading">
                      <div>
                        <h3>Recovery, in perspective</h3>
                        <p>Predicted vs. observed heart rate</p>
                      </div>
                      <ProvenanceChip source={prediction?.provenance} />
                    </div>
                    <RecoveryChart prediction={prediction} />
                    <div className="chart-legend">
                      <span>
                        <i className="line-swatch" />
                        Observed
                      </span>
                      <span>
                        <i className="line-swatch dashed" />
                        Predicted
                      </span>
                      <span className="rmse">
                        RMSE <b>{value(prediction?.rmse, 2)} bpm</b>
                      </span>
                    </div>
                  </Card>
                </div>
              </div>
              <div className="vitals-strip">
                {[
                  {
                    name: "Respiration",
                    field: "respiration_brpm",
                    unit: "br/min",
                    icon: Wind,
                  },
                  {
                    name: "Blood oxygen",
                    field: "spo2_pct",
                    unit: "%",
                    icon: Activity,
                  },
                  {
                    name: "Recorded steps",
                    field: "steps",
                    unit: "steps",
                    icon: Footprints,
                  },
                ].map((m) => (
                  <div key={m.field}>
                    <m.icon size={18} />
                    <span>
                      {m.name}
                      <small>
                        {quality[m.field]
                          ? new Date(
                              quality[m.field].event_time,
                            ).toLocaleString(undefined, {
                              month: "short",
                              day: "numeric",
                              hour: "2-digit",
                              minute: "2-digit",
                            })
                          : "No measurement"}
                      </small>
                    </span>
                    <b>
                      {value(
                        latest?.[m.field as keyof typeof latest] as
                          | number
                          | null,
                        1,
                      )}
                      <small>{m.unit}</small>
                    </b>
                    <ProvenanceChip source={source(m.field)} />
                  </div>
                ))}
              </div>
              {Object.values(quality).some((q) => q.contested) && (
                <div className="notice">
                  Connected sources disagree on some measurements. See Signals
                  for the competing readings.
                </div>
              )}
              <div className="bottom-grid">
                <Card className="daily-card">{planContent}</Card>
                <Card className="twin-insight">
                  <div className="insight-icon">
                    <Sparkles size={22} />
                  </div>
                  <span className="eyebrow">A CONVERSATION WITH YOUR DATA</span>
                  <h3>
                    “What is my body
                    <br />
                    telling me today?”
                  </h3>
                  <p>
                    Your twin puts your measurements into words. Grounded in
                    your data. Personal to your pattern.
                  </p>
                  <div className="suggestion-pills">
                    {["Why am I tired?", "How is my recovery?"].map((q) => (
                      <button
                        key={q}
                        onClick={() => {
                          setChat(true);
                          ask(q);
                        }}
                      >
                        {q}
                        <MoveUpRight size={12} />
                      </button>
                    ))}
                  </div>
                  <button className="text-button" onClick={() => setChat(true)}>
                    Start a conversation <ArrowRight size={15} />
                  </button>
                </Card>
              </div>
            </>
          )}
          {state && page === "Signals" && (
            <>
              <div className="section-toolbar">
                <p>Recorded measurements, with their source and time intact.</p>
                <div className="segmented">
                  {[1, 7, 28].map((d) => (
                    <button
                      className={days === d ? "selected" : ""}
                      key={d}
                      onClick={() => setDays(d)}
                    >
                      {d === 1 ? "24 hours" : `${d} days`}
                    </button>
                  ))}
                </div>
              </div>
              <div className="two-col">
                {[
                  { field: "heart_rate_bpm", title: "Heart rate", unit: "bpm" },
                  {
                    field: "hrv_rmssd_ms",
                    title: "Heart-rate variability · RMSSD",
                    unit: "ms",
                  },
                  {
                    field: "resting_hr_bpm",
                    title: "Resting heart rate",
                    unit: "bpm",
                  },
                  {
                    field: "respiration_brpm",
                    title: "Respiration",
                    unit: "br/min",
                  },
                  { field: "spo2_pct", title: "Blood oxygen", unit: "%" },
                  { field: "steps", title: "Recorded steps", unit: "steps" },
                ].map((m) => (
                  <Card key={m.field}>
                    <div className="card-heading">
                      <h3>{m.title}</h3>
                      <ProvenanceChip source={source(m.field)} />
                    </div>
                    <SignalChart
                      data={metrics[m.field] ?? []}
                      unit={m.unit}
                      days={days}
                    />
                    {quality[m.field]?.contested && (
                      <p className="notice">
                        Source disagreement:{" "}
                        {quality[m.field].alternatives
                          ?.map((a: any) => `${humanize(a.source)}: ${a.value}`)
                          .join(" · ")}
                      </p>
                    )}
                  </Card>
                ))}
                <Card>
                  <div className="card-heading">
                    <h3>Your nights, in layers</h3>
                    <ProvenanceChip source={source("sleep")} />
                  </div>
                  <SleepChart data={sleep} />
                  <div className="chart-legend">
                    <span>Deep</span>
                    <span>Light</span>
                    <span>REM</span>
                    <span>Awake · minutes</span>
                  </div>
                </Card>
                <Card>
                  <div className="card-heading">
                    <h3>Readiness over time</h3>
                    <ProvenanceChip source={state.provenance_banner} />
                  </div>
                  <ReadinessChart
                    data={history}
                    cuts={state.readiness.cuts ?? [17, 33, 50, 67, 83]}
                  />
                </Card>
              </div>
              <Card className="model-card">
                <div>
                  <span className="eyebrow">THE MODEL, OPENLY</span>
                  <h3>Personal recovery fit</h3>
                  <p>
                    {state.baseline_summary.prior_label}. Band width is ±2
                    held-out RMSE; it is not a calibrated confidence interval.
                  </p>
                </div>
                <div className="model-stat">
                  <b>
                    {value(state.baseline_summary.recovery_tau_s, 1)}
                    <small>s</small>
                  </b>
                  <span>Recovery time constant</span>
                </div>
                <div className="model-stat">
                  <b>{value(state.baseline_summary.tau_fit_n_sessions)}</b>
                  <span>Accepted sessions</span>
                </div>
                <div className="model-stat">
                  <b>
                    {value(state.baseline_summary.tau_fit_rmse, 2)}
                    <small>bpm</small>
                  </b>
                  <span>Held-out mean error</span>
                </div>
                <button
                  className="button"
                  onClick={async () => {
                    try {
                      await post("/api/baseline/recompute");
                      notify("Personal model recomputed.");
                      changed();
                    } catch (e) {
                      notify((e as Error).message);
                    }
                  }}
                >
                  Refit model
                </button>
              </Card>
              {state.readiness.degraded_reason && (
                <p className="notice">
                  {state.readiness.degraded_reason}. Readiness confidence is
                  reduced.
                </p>
              )}
            </>
          )}
          {state && page === "Daily plan" && (
            <>
              <div className="two-col plan-page">
                <Card>{planContent}</Card>
                <Card>
                  <span className="eyebrow">BUILT AROUND REAL LIFE</span>
                  <h3>A plan that respects your calendar.</h3>
                  <p>
                    Available windows are checked against your selected
                    calendars. Before an event is added, BioTwin checks for
                    conflicts again.
                  </p>
                  <div className="planning-rules">
                    <div>
                      <ShieldCheck size={19} />
                      <span>No overlaps with busy events</span>
                    </div>
                    <div>
                      <Moon size={19} />
                      <span>Naps end at least six hours before bedtime</span>
                    </div>
                    <div>
                      <Battery size={19} />
                      <span>Workout intensity follows readiness</span>
                    </div>
                    <div>
                      <CalendarDays size={19} />
                      <span>Your chosen session includes a reminder</span>
                    </div>
                  </div>
                  <button
                    className="button"
                    onClick={() => navigate("Connections")}
                  >
                    Manage calendar & preferences <ArrowUpRight size={15} />
                  </button>
                </Card>
              </div>
              <Card className="availability">
                <div className="card-heading">
                  <div>
                    <span className="eyebrow">EXPERIMENTAL DAY OUTLOOK</span>
                    <h3>Your possible rhythm ahead</h3>
                  </div>
                  <ProvenanceChip source="simulated" />
                </div>
                <OutlookChart outlook={outlook} />
                <p className="small-note">{outlook?.assumptions}</p>
              </Card>
              <Card className="availability">
                <div className="card-heading">
                  <h3>Today's busy windows</h3>
                  <span className="muted">{plan?.timezone}</span>
                </div>
                {plan?.busy.length ? (
                  <div className="busy-list">
                    {plan.busy.map((b, i) => (
                      <div key={i}>
                        <i />
                        <span>
                          {new Date(b.start).toLocaleTimeString(undefined, {
                            hour: "2-digit",
                            minute: "2-digit",
                            timeZone: plan.timezone,
                          })}{" "}
                          —{" "}
                          {new Date(b.end).toLocaleTimeString(undefined, {
                            hour: "2-digit",
                            minute: "2-digit",
                            timeZone: plan.timezone,
                          })}
                        </span>
                        <b>{b.title}</b>
                      </div>
                    ))}
                  </div>
                ) : (
                  <p>
                    {plan?.calendar_status === "connected"
                      ? "No busy windows returned for today."
                      : "Connect a calendar to see verified busy windows."}
                  </p>
                )}
              </Card>
            </>
          )}
          {state && page === "What-if lab" && (
            <>
              <div className="lab-notice">
                <FlaskConical size={20} />
                <div>
                  <b>A space to explore, not a promise.</b>
                  <p>
                    Scenarios use explicit assumptions. They don’t predict the
                    effect of an intervention on your health.
                  </p>
                </div>
                {simulation && <ProvenanceChip source="simulated" />}
              </div>
              <div className="lab-grid">
                <Avatar
                  live={live}
                  overlay={overlay}
                  state={state}
                  reduced={reduced}
                />
                <div>
                  <Card>
                    <span className="eyebrow">CHOOSE A POSSIBLE NEXT STEP</span>
                    <h3>What if I…</h3>
                    <div className="scenario-options">
                      {[
                        {
                          id: "rest",
                          title: "Take a breather",
                          text: "Pause and rest",
                          icon: Leaf,
                        },
                        {
                          id: "light",
                          title: "Keep it light",
                          text: "Gentle movement",
                          icon: Footprints,
                        },
                        {
                          id: "exercise",
                          title: "Get moving",
                          text: "An exercise scenario",
                          icon: Activity,
                        },
                      ].map((s) => (
                        <button
                          key={s.id}
                          className={
                            simulation?.scenario === s.id ? "selected" : ""
                          }
                          onClick={() => simulate(s.id)}
                          disabled={!!scenarioBusy}
                        >
                          <s.icon size={23} />
                          <span>
                            <b>{s.title}</b>
                            <small>{s.text}</small>
                          </span>
                          {scenarioBusy === s.id ? (
                            <LoaderCircle className="spin" size={17} />
                          ) : (
                            <ArrowUpRight size={17} />
                          )}
                        </button>
                      ))}
                    </div>
                    {simulation && (
                      <button
                        className="text-button"
                        onClick={() => {
                          overlay.current = null;
                          setSimulation(null);
                        }}
                      >
                        Return to recorded state <ArrowRight size={14} />
                      </button>
                    )}
                  </Card>
                  <Card className="lab-chart">
                    <div className="card-heading">
                      <h3>
                        {simulation
                          ? "SIMULATED heart-rate trajectory"
                          : "Your current recovery prediction"}
                      </h3>
                      <ProvenanceChip
                        source={
                          simulation ? "simulated" : prediction?.provenance
                        }
                      />
                    </div>
                    <RecoveryChart
                      prediction={prediction}
                      simulation={simulation}
                    />
                    <p className="small-note">
                      {simulation?.assumption ?? prediction?.assumption}
                    </p>
                  </Card>
                </div>
              </div>
            </>
          )}
          {page === "Connections" && (
            <Connections
              session={session}
              onAuth={() => setAuth(true)}
              onChange={changed}
              notify={notify}
            />
          )}
          <footer>
            <span>
              <Leaf size={13} />
              Made for your everyday wellbeing.
            </span>
            <span>
              Wellness estimates ·{" "}
              {state?.baseline_summary.model_version ?? "recovery-1.0.0"}
            </span>
            <label>
              <input
                type="checkbox"
                checked={reduced}
                onChange={(e) => setReduced(e.target.checked)}
              />
              Reduced motion
            </label>
          </footer>
        </main>
      </div>
      {chat && (
        <div className="chat-backdrop" onClick={() => setChat(false)}>
          <aside
            className="chat-panel"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Talk to your twin"
          >
            <div className="chat-header">
              <span className="chat-avatar">
                <AudioLines size={24} />
              </span>
              <div>
                <h3>Your twin</h3>
                <span>Grounded in your measurements</span>
              </div>
              <button
                className="icon-btn"
                aria-label="Close conversation"
                onClick={() => setChat(false)}
              >
                <X size={19} />
              </button>
            </div>
            <div className="chat-messages">
              <div className="chat-welcome">
                <Sparkles size={24} />
                <h2>
                  A little clarity,
                  <br />
                  whenever you need it.
                </h2>
                <p>Ask about your readiness, sleep, recovery, or plan.</p>
                <div className="chat-prompts">
                  {[
                    "Why am I tired today?",
                    "How is my recovery trending?",
                    "What is my plan today?",
                  ].map((q) => (
                    <button onClick={() => ask(q)} key={q}>
                      {q}
                      <ArrowUpRight size={14} />
                    </button>
                  ))}
                </div>
              </div>
              {messages.map((m, i) => (
                <div key={i} className={`message ${m.role}`}>
                  <small>{m.role === "user" ? "YOU" : "YOUR TWIN"}</small>
                  <p>{m.text}</p>
                  {m.reply && (
                    <button
                      className="listen-button"
                      onClick={() => speak(m.reply!)}
                    >
                      <Volume2 size={13} />
                      Listen with ElevenLabs
                    </button>
                  )}
                </div>
              ))}
              {asking && (
                <div className="thinking">
                  <LoaderCircle size={15} className="spin" />
                  Reading your computed context…
                </div>
              )}
              <div ref={messagesEnd} />
            </div>
            <div className="chat-input-area">
              {speaking && (
                <button
                  className="text-button"
                  onClick={() => {
                    audio.current?.pause();
                    setSpeaking(false);
                  }}
                >
                  <Pause size={14} />
                  Stop speaking
                </button>
              )}
              <form
                className="chat-input"
                onSubmit={(e: FormEvent) => {
                  e.preventDefault();
                  ask(question);
                }}
              >
                <input
                  aria-label="Ask your twin"
                  value={question}
                  maxLength={1000}
                  onChange={(e) => setQuestion(e.target.value)}
                  placeholder="Ask your twin something…"
                />
                <button
                  type="button"
                  className="icon-btn"
                  aria-label="Dictate a question"
                  onClick={microphone}
                >
                  <Mic size={17} />
                </button>
                <button
                  className="send-button"
                  aria-label="Send question"
                  disabled={asking || !question.trim()}
                >
                  <Send size={17} />
                </button>
              </form>
              <p>Computed insights, expressed in words. No diagnoses.</p>
            </div>
          </aside>
        </div>
      )}
      {auth && <AuthModal onClose={() => setAuth(false)} onDone={changed} />}
      {toast && (
        <div className="toast" role="status">
          <span>{toast}</span>
          <button
            aria-label="Dismiss notification"
            onClick={() => setToast("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
      {showOps && (
        <div className="modal-backdrop" onClick={() => setShowOps(false)}>
          <section
            className="auth-modal ops-modal"
            onClick={(e) => e.stopPropagation()}
            role="dialog"
            aria-label="System status"
          >
            <button
              className="close"
              aria-label="Close system status"
              onClick={() => setShowOps(false)}
            >
              ×
            </button>
            <ShieldCheck size={24} />
            <h2>System status</h2>
            <p>
              Connection and pipeline diagnostics. No personal measurement
              values are logged here.
            </p>
            <pre>{ops ? JSON.stringify(ops, null, 2) : "Loading…"}</pre>
          </section>
        </div>
      )}
    </div>
  );
}
