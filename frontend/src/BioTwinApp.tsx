import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  AudioLines,
  CalendarDays,
  Check,
  ChevronRight,
  History,
  LayoutGrid,
  Leaf,
  Link2,
  LoaderCircle,
  Mic,
  Pause,
  Radio,
  Send,
  Volume2,
  X,
} from "lucide-react";
import Connections, { AuthModal } from "./Connections";
import { api, post, value, type DayScenario } from "./api";
import { SimulateDayChart, TrajectoryChart } from "./Charts";
import { useDashboard } from "./useDashboard";
import { CalendarAgenda, CalendarEditor } from "./CalendarAgenda";
import type { CalendarDraft } from "./useCalendar";
import { useTwinConversation } from "./useTwinConversation";
import { questionTopic, type Topic } from "./topics";
import {
  CalendarDay,
  hasCurrentMetric,
  Metric,
  Panel,
  PanelTitle,
  PlanPanel,
  Range,
  ReadinessDetails,
  ReadinessPanel,
  SignalDetail,
  signalDefinitions,
  TomorrowPanel,
  topicSignal,
} from "./DashboardPanels";
import type { CaptionWord } from "./captions";
import { BestWindowCard, DayForecast, FuturePaths } from "./TrainingWindow";
import { spokenFocus, spokenSoFar, wantsComparison } from "./trainingFocus";

type Page =
  "Overview" | "Signals" | "Daily plan" | "Connections";
const navigation = [
  { name: "Overview", icon: LayoutGrid },
  { name: "Signals", icon: Activity },
  { name: "Daily plan", icon: CalendarDays },
  { name: "Connections", icon: Link2 },
] as const;
const descriptions: Record<Page, string> = {
  Overview: "A little awareness. A better day.",
  Signals: "The small signals that tell your story.",
  "Daily plan": "A little space for what you need.",
  Connections: "Your watch, your schedule, your rhythm.",
};
const topicTitles: Record<Topic, string> = {
  heart: "A closer look at your heart",
  sleep: "Let's talk about sleep",
  calories: "Your energy in motion",
  steps: "Every step adds up",
  plan: "Let's find your window",
  recovery: "Your recovery, understood",
};

function Captions({
  words,
  time,
  answer,
}: {
  words: CaptionWord[];
  time: number;
  answer: string;
}) {
  const active = words.findIndex((w) => time >= w.start && time < w.end);
  const index =
    active >= 0
      ? active
      : Math.max(
          0,
          words.findLastIndex((w) => w.start <= time),
        );
  const start = Math.floor(index / 12) * 12;
  return (
    <p
      className="live-caption"
      data-testid="live-caption"
      aria-label="Twin captions"
    >
      {words.length
        ? words.slice(start, start + 12).map((word, i) => (
            <span
              key={`${start + i}:${word.start}`}
              data-active={start + i === active ? "true" : "false"}
              className={start + i <= index ? "spoken" : ""}
            >
              {word.text}{" "}
            </span>
          ))
        : answer}
    </p>
  );
}

export default function BioTwinApp() {
  const data = useDashboard();
  const { state, session, status } = data;
  const [page, setPage] = useState<Page>(() =>
    new URLSearchParams(location.search).get("connected")?.includes("calendar")
      ? "Daily plan"
      : "Overview",
  );
  const [eventEditor, setEventEditor] = useState<CalendarDraft | "new" | null>(
    null,
  );
  const [auth, setAuth] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [forecastOpen, setForecastOpen] = useState(false);
  const [compare, setCompare] = useState(false);
  const [scenarioId, setScenarioId] =
    useState<DayScenario["id"]>("extra_steps");
  const [daySteps, setDaySteps] = useState(5000);
  const [takeover, setTakeover] = useState<{
    topic: Topic;
    question: string;
    automatic: boolean;
  } | null>(null);
  const [reminder, setReminder] = useState(10);
  const [adding, setAdding] = useState("");
  const [added, setAdded] = useState<string[]>([]);
  const [reduced, setReduced] = useState(
    () => matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  const input = useRef<HTMLInputElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const autoTopic = useRef(false);
  const conversation = useTwinConversation({
    open: true,
    online: status === "online",
    bundle: data.bundle,
    session,
    accountKey: data.accountKey,
    calendarRange: { start: data.calendar.start, end: data.calendar.end },
    onCalendarDraft: (draft) => {
      autoTopic.current = false;
      setTakeover(null);
      setPage("Daily plan");
      setEventEditor(draft);
    },
    onCalendarEvent: () => {
      autoTopic.current = false;
      setTakeover(null);
      setEventEditor(null);
      setPage("Daily plan");
      void data.calendar.refresh();
      void data.refreshPlan();
      data.notify("Added to your Google Calendar. Your agenda is updating.");
    },
    onQuestion: (text, calendarMode) => {
      const topic = calendarMode ? "plan" : questionTopic(text);
      setCompare(wantsComparison(text));
      setPage("Overview");
      setHistoryOpen(false);
      autoTopic.current = !!topic;
      setTakeover(topic ? { topic, question: text, automatic: true } : null);
      window.scrollTo({ top: 0, behavior: "instant" });
    },
    onSpeechEnd: () => {
      if (autoTopic.current) {
        autoTopic.current = false;
        setTakeover(null);
        setPage("Overview");
        window.scrollTo({ top: 0, behavior: "instant" });
      }
    },
  });
  const {
    speaking,
    listening,
    asking,
    transcribing,
    voiceLoop,
    wakeListening,
  } = conversation;
  const phase = listening
    ? "Listening"
    : transcribing
      ? "Transcribing"
      : asking
        ? "Thinking"
        : speaking
          ? "Speaking"
          : voiceLoop
            ? "Waiting for you"
            : wakeListening
              ? "Say Hey twin"
              : "Here with you";
  useEffect(() => {
    setAdded([]);
    setEventEditor(null);
    setTakeover(null);
    setCompare(false);
    autoTopic.current = false;
  }, [data.accountKey]);
  useEffect(() => {
    if (data.daySimulation?.available)
      setDaySteps(data.daySimulation.controls.steps);
  }, [data.daySimulation]);
  useEffect(() => {
    const editable = (target: EventTarget | null) => {
      const element = target as HTMLElement | null;
      return (
        element?.isContentEditable ||
        ["INPUT", "TEXTAREA", "SELECT", "BUTTON"].includes(
          element?.tagName ?? "",
        )
      );
    };
    const keydown = (e: KeyboardEvent) => {
      if (
        e.code !== "Space" ||
        e.repeat ||
        e.metaKey ||
        e.ctrlKey ||
        e.altKey ||
        editable(e.target)
      )
        return;
      e.preventDefault();
      setPage("Overview");
      setHistoryOpen(false);
      conversation.microphone();
    };
    document.addEventListener("keydown", keydown);
    return () => document.removeEventListener("keydown", keydown);
  }, [conversation]);
  useEffect(() => {
    if (!historyOpen) return;
    const previous = document.activeElement as HTMLElement | null;
    const dialog = transcript.current;
    dialog?.querySelector<HTMLButtonElement>("button")?.focus();
    const keydown = (e: KeyboardEvent) => {
      if (e.key === "Escape") setHistoryOpen(false);
      if (e.key === "Tab" && dialog) {
        const controls = [
          ...dialog.querySelectorAll<HTMLElement>(
            'button:not(:disabled), [href], input, [tabindex="0"]',
          ),
        ];
        const first = controls[0],
          last = controls.at(-1);
        if (e.shiftKey && document.activeElement === first) {
          e.preventDefault();
          last?.focus();
        }
        if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first?.focus();
        }
      }
    };
    document.addEventListener("keydown", keydown);
    return () => {
      document.removeEventListener("keydown", keydown);
      previous?.focus();
    };
  }, [historyOpen]);
  function navigate(next: Page) {
    autoTopic.current = false;
    setTakeover(null);
    setPage(next);
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function dismiss() {
    autoTopic.current = false;
    setTakeover(null);
    setPage("Overview");
  }
  function explore(topic: Topic) {
    setTakeover({ topic, question: "", automatic: false });
    autoTopic.current = false;
    setPage("Overview");
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  async function book(id: string) {
    if (!session || session.demo) {
      setAuth(true);
      return;
    }
    setAdding(id);
    try {
      await post("/api/calendar/events", {
        proposal_id: id,
        reminder_minutes: reminder,
      });
      setAdded((ids) => [...ids, id]);
      data.notify(`Added to your calendar with a ${reminder}-minute reminder.`);
      void data.calendar.refresh();
    } catch (error) {
      data.notify(
        (error as Error).message ||
          "Your event could not be added. Please try again.",
      );
    } finally {
      setAdding("");
    }
  }
  const actions = { reminder, setReminder, adding, added, book };
  // The measured Garmin level, not energy_reserve_pct: that one is readiness
  // rescaled by recovery progress, an estimate, and this tile says "current".
  const battery = state?.latest?.body_battery_pct ?? null;
  const batteryAt = state?.quality?.body_battery_pct?.event_time;
  const visibleSignals = signalDefinitions.filter((m) =>
    hasCurrentMetric(m.field, data),
  );
  const overviewTopics: Record<string, Topic> = {
    heart_rate_bpm: "heart",
    sleep: "sleep",
    active_kcal: "calories",
    steps: "steps",
  };
  const overviewSignals = signalDefinitions
    .filter((m) => m.field in overviewTopics)
    .filter((m) => hasCurrentMetric(m.field, data));
  const recentReply = conversation.messages
    .filter((m) => m.role === "twin")
    .at(-1);
  const answer = recentReply?.text ?? "";
  const focus = spokenFocus(
    speaking
      ? spokenSoFar(conversation.captionWords, conversation.audioTime) ||
          conversation.activeAnswer
      : answer,
    data.decision,
  );
  const decisionCards = (
    <>
      <div className="decision-grid">
        <BestWindowCard
          decision={data.decision}
          focus={focus}
          onCompare={() => setCompare(true)}
        />
        <DayForecast decision={data.decision} focus={focus} />
      </div>
      {compare && (
        <FuturePaths
          decision={data.decision}
          focus={focus}
          onClose={() => setCompare(false)}
        />
      )}
    </>
  );
  const talk = () => {
    navigate("Overview");
    requestAnimationFrame(() => input.current?.focus());
  };
  const daySimulation = data.daySimulation?.available
    ? data.daySimulation
    : null;
  const activeScenario =
    daySimulation?.scenarios.find((s) => s.id === scenarioId) ??
    daySimulation?.scenarios.find((s) => s.id === "extra_steps") ??
    daySimulation?.baseline;
  const navButtons = navigation.map((item) => (
    <button
      key={item.name}
      aria-current={page === item.name ? "page" : undefined}
      className={page === item.name ? "selected" : ""}
      onClick={() => navigate(item.name)}
    >
      <item.icon size={20} strokeWidth={1.7} />
      <span>{item.name}</span>
    </button>
  ));
  const voiceControls = (
    <div className="voice-feedback">
      {conversation.voiceNotice && (
        <p role={conversation.voiceError ? "alert" : "status"}>
          {conversation.voiceError
            ? /microphone|recording|transcri/i.test(conversation.voiceNotice)
              ? conversation.voiceNotice
              : "Your twin’s voice is unavailable. You can keep talking by text."
            : conversation.voiceNotice}
        </p>
      )}
      {conversation.needsTap && (
        <button className="text-button" onClick={conversation.resumeSpeech}>
          <Volume2 size={16} />
          Tap to hear your twin
        </button>
      )}
      {speaking && (
        <button className="text-button" onClick={conversation.stopSpeaking}>
          <Pause size={14} />
          Stop speaking
        </button>
      )}
      {voiceLoop && (
        <button className="text-button" onClick={conversation.deactivateVoice}>
          <X size={14} />
          End voice chat
        </button>
      )}
    </div>
  );
  const replyPanel = (
    <div className="answer-panel" data-testid="answer-panel">
      <div className="answer-label">
        <AudioLines size={17} />
        <b>Your twin</b>
        <span>{phase}</span>
      </div>
      {asking ? (
        <p className="answer-loading">
          <LoaderCircle size={16} className="spin" />
          Looking at your measurements…
        </p>
      ) : speaking ? (
        <Captions
          words={conversation.captionWords}
          time={conversation.audioTime}
          answer={conversation.activeAnswer}
        />
      ) : (
        <p className="answer-text">
          {answer || "Ask a question to explore this with your twin."}
        </p>
      )}
      {recentReply?.reply?.notice && (
        <p className="fine-print">{recentReply.reply.notice}</p>
      )}
      {voiceControls}
    </div>
  );
  return (
    <div
      className={`biotwin-app${takeover ? " has-takeover" : ""}${reduced ? " reduced-motion" : ""}`}
    >
      <aside className="desktop-nav">
        <button className="wordmark" onClick={() => navigate("Overview")}>
          <span className="brand-symbol">
            <Leaf size={22} />
          </span>
          bio<span>twin</span>
          <i />
        </button>
        <div className="nav-caption">YOUR PERSONAL SPACE</div>
        <nav aria-label="Main navigation">{navButtons}</nav>
        <div className="nav-bottom">
          <button
            className="account-control"
            onClick={() =>
              session && !session.demo ? navigate("Connections") : setAuth(true)
            }
          >
            <span>
              {session && !session.demo ? session.user.name?.[0] || "S" : "B"}
            </span>
            <div>
              <b>
                {session && !session.demo
                  ? session.user.name || "Your account"
                  : "Log in"}
              </b>
              <small>
                {session && !session.demo
                  ? "Account & preferences"
                  : "Sign in or create an account"}
              </small>
            </div>
            <ChevronRight size={16} />
          </button>
        </div>
      </aside>
      <header className="persistent-bar">
        <button
          className="mobile-brand"
          aria-label="BioTwin Overview"
          onClick={() => navigate("Overview")}
        >
          <Leaf size={22} />
        </button>
        <div
          className="body-battery"
          title="Your Garmin Body Battery, as measured by the watch. Not a BioTwin estimate."
          aria-label={`Body Battery ${battery == null ? "awaiting a reading" : `${battery} percent`}`}
        >
          <div>
            <b>Body Battery</b>
            <small>
              {status === "offline"
                ? "Offline example"
                : battery == null
                  ? "Awaiting a reading"
                  : batteryAt
                    ? `Current · ${new Date(batteryAt).toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" })}`
                    : "Current"}
            </small>
          </div>
          <div
            className={`battery-cell ${battery != null && battery < 30 ? "low" : ""}`}
            role="meter"
            aria-label="Body Battery, measured"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={battery ?? undefined}
          >
            <span style={{ width: `${battery ?? 0}%` }} />
            <b>{battery == null ? "—" : `${battery}%`}</b>
          </div>
          <button
            className="bar-twin battery-forecast"
            onClick={() => setForecastOpen(true)}
            aria-label="Battery Forecast: where the model expects this to go"
            title="Battery Forecast"
          >
            <Radio size={16} />
            <span>Battery Forecast</span>
          </button>
        </div>
      </header>
      <main className="workspace" id="main-content">
        <div className="page-intro">
          {page !== "Overview" && (
            <div>
              <span className="eyebrow">
                {new Date().toLocaleDateString(undefined, {
                  weekday: "long",
                  month: "long",
                  day: "numeric",
                })}
              </span>
              <h1>{page}</h1>
              <p>{descriptions[page]}</p>
            </div>
          )}
        </div>
        {status === "offline" && (
          <div className="notice offline-notice" role="status">
            You're viewing an offline example. Your personal measurements aren't
            updating.<button onClick={data.reset}>Reconnect</button>
          </div>
        )}
        {!state && (
          <div className="loading-screen">
            <LoaderCircle size={24} className="spin" />
            <p>Getting your twin ready…</p>
          </div>
        )}
        {state && page === "Overview" && (
          <section
            className={`twin-hero glass ${takeover ? "focused" : ""}`}
            aria-label="Your digital twin"
          >
            <div className="hero-copy">
              <span className="eyebrow">
                <i />
                YOUR DIGITAL TWIN
              </span>
              <h2>
                Beyond
                <br />
                <em>Numbers</em>
              </h2>
              <p>
                Wearables give you numbers.
                <br />
                BioTwin gives you understanding.
              </p>
              <div className="hero-prompts">
                {["How did I sleep?", "When should I work out?"].map((q) => (
                  <button
                    disabled={asking}
                    key={q}
                    onClick={() => conversation.ask(q)}
                  >
                    {q}
                    <ArrowUpRight size={13} />
                  </button>
                ))}
              </div>
            </div>
            <div className="hero-avatar">
              <div
                className={`coach-presence ${listening ? "listening" : ""}${speaking ? " speaking" : ""}${asking || transcribing ? " thinking" : ""}`}
                aria-label={`BioTwin coach ${phase}`}
              >
                <div className="coach-portrait">
                  <img src="/assets/coach-mascot.png" alt="" />
                </div>
                <div className="coach-control">
                  <button
                    type="button"
                    className={`coach-mic ${listening ? "listening" : ""}`}
                    disabled={asking}
                    aria-label={listening ? "Stop listening" : "Start listening"}
                    aria-pressed={listening}
                    onClick={conversation.microphone}
                  >
                    <span aria-hidden="true" />
                    <Mic size={24} />
                  </button>
                  <div className="coach-status">
                    <b>{phase}</b>
                    <span>
                      {listening
                        ? "Say it naturally"
                        : speaking
                          ? "Answering out loud"
                          : asking || transcribing
                            ? "Reading the room"
                            : wakeListening
                              ? "Say Hey twin"
                              : voiceLoop
                                ? "Waiting for you"
                                : "Tap the mic"}
                    </span>
                  </div>
                </div>
              </div>
            </div>
            <div className="hero-composer">
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void conversation.ask(conversation.question);
                }}
              >
                <button
                  type="button"
                  className={`microphone ${listening ? "listening" : ""}`}
                  disabled={asking}
                  aria-label={listening ? "Stop listening" : "Start listening"}
                  aria-pressed={listening}
                  onClick={conversation.microphone}
                >
                  <Mic size={20} />
                </button>
                <input
                  ref={input}
                  aria-label="Ask your twin"
                  value={conversation.question}
                  onChange={(e) => conversation.setQuestion(e.target.value)}
                  placeholder={
                    listening
                      ? "Listening… tap the mic when you're done"
                      : "Ask your twin anything about your day…"
                  }
                  maxLength={1000}
                />
                <button
                  className="send-question"
                  aria-label="Send question"
                  disabled={asking || !conversation.question.trim()}
                >
                  {asking ? (
                    <LoaderCircle size={18} className="spin" />
                  ) : (
                    <Send size={18} />
                  )}
                </button>
              </form>
            </div>
          </section>
        )}
        {state &&
          page === "Overview" &&
          (takeover ? (
            <section
              className="topic-takeover glass"
              data-testid="topic-takeover"
              data-topic={takeover.topic}
              aria-label={topicTitles[takeover.topic]}
            >
              <div className="takeover-heading">
                <button
                  className="icon-btn"
                  aria-label="Back to Overview"
                  onClick={dismiss}
                >
                  <ArrowLeft size={19} />
                </button>
                <div>
                  <span className="eyebrow">A CLOSER LOOK</span>
                  <h2>{topicTitles[takeover.topic]}</h2>
                </div>
                <span className="pill green">
                  <AudioLines size={13} />
                  {phase}
                </span>
              </div>
              <div className="takeover-scroll">
                {takeover.question && (
                  <p className="asked-question">“{takeover.question}”</p>
                )}
                {topicSignal[takeover.topic] ? (
                  <SignalDetail
                    field={topicSignal[takeover.topic]!}
                    data={data}
                  />
                ) : takeover.topic === "plan" ? (
                  <>
                    {decisionCards}
                    <CalendarAgenda
                      calendar={data.calendar}
                      compact
                      onConnect={() => navigate("Connections")}
                      onNew={() => setEventEditor("new")}
                      onAsk={(q) => void conversation.ask(q, true)}
                      asking={asking}
                    />
                    <PlanPanel data={data} actions={actions} />
                  </>
                ) : (
                  <>
                    <ReadinessPanel data={data} />
                    <TomorrowPanel data={data} />
                  </>
                )}
              </div>
              {replyPanel}
            </section>
          ) : (
            <>
              {(asking || answer || conversation.voiceNotice) && (
                <div className="inline-answer glass">
                  {replyPanel}
                  <button
                    className="text-button"
                    onClick={() => setHistoryOpen(true)}
                  >
                    Open conversation history <ArrowUpRight size={14} />
                  </button>
                </div>
              )}
              {decisionCards}
              <div className="section-label">
                <h2>Your essentials</h2>
                <button onClick={() => navigate("Signals")}>
                  All signals <ArrowUpRight size={14} />
                </button>
              </div>
              <div className="essentials-grid">
                {overviewSignals.map((m) => (
                  <Metric
                    key={m.field}
                    field={m.field}
                    data={data}
                    onClick={() =>
                      explore(overviewTopics[m.field] ?? "heart")
                    }
                  />
                ))}
                {!overviewSignals.length && (
                  <div className="empty-state">
                    <Activity size={22} />
                    <p>Connect wearable data to fill this overview.</p>
                  </div>
                )}
              </div>
              {/* Body Battery's own projected curve already lives in "Your day ahead"
                  above (decisionCards), with the calendar overlay and MATLAB detail
                  TomorrowPanel doesn't have -- showing it again here was the same
                  trajectory twice on one screen. Readiness's own recommendations stay,
                  since nothing else on this page covers them. */}
              <ReadinessPanel data={data} />
              <div className="section-label">
                <h2>A little room for yourself</h2>
                <button onClick={() => navigate("Daily plan")}>
                  Your daily plan <ArrowUpRight size={14} />
                </button>
              </div>
              <PlanPanel data={data} actions={actions} />
            </>
          ))}
        {state && page === "Signals" && (
          <>
            <div className="section-label">
              <h2>Your measurements</h2>
              <Range data={data} />
            </div>
            <div className="signals-grid">
              {visibleSignals.map((m) => (
                <Panel key={m.field}>
                  <SignalDetail field={m.field} data={data} />
                </Panel>
              ))}
              {!visibleSignals.length && (
                <Panel>
                  <div className="empty-state">
                    <Activity size={22} />
                    <p>Connect wearable data to show your measurements.</p>
                  </div>
                </Panel>
              )}
            </div>
            <ReadinessDetails data={data} />
          </>
        )}
        {page === "Daily plan" && (
          <>
            <CalendarAgenda
              calendar={data.calendar}
              onConnect={() => navigate("Connections")}
              onNew={() => setEventEditor("new")}
              onAsk={(q) => void conversation.ask(q, true)}
              asking={asking}
            />
            <div className="plan-layout">
              <PlanPanel data={data} actions={actions} />
              <CalendarDay data={data} />
            </div>
            <Panel className="plan-guidance">
              <Leaf size={23} className="green" />
              <div>
                <h3>Built around real life.</h3>
                <p>
                  We check your calendar before booking. Movement follows your
                  readiness; naps leave room before bedtime. You choose what
                  gets added.
                </p>
              </div>
              <button
                className="button"
                onClick={() => navigate("Connections")}
              >
                Calendar & preferences
                <ArrowUpRight size={15} />
              </button>
            </Panel>
          </>
        )}
        {eventEditor && (
          <CalendarEditor
            key={
              eventEditor === "new" ? `new-${data.accountKey}` : eventEditor.id
            }
            draft={eventEditor}
            calendar={data.calendar}
            onClose={() => setEventEditor(null)}
            onAdded={(start) => {
              setEventEditor(null);
              autoTopic.current = false;
              setTakeover(null);
              setPage("Daily plan");
              data.calendar.setStart(start);
              void data.calendar.refresh();
              void data.refreshPlan();
              data.notify("Added to your calendar. Your agenda is updating.");
            }}
          />
        )}
        <div hidden={page !== "Connections"}>
          <Connections
            session={session}
            onAuth={() => setAuth(true)}
            onChange={() => {
              conversation.reset();
              data.reset();
            }}
            notify={data.notify}
            state={state ?? undefined}
          />
        </div>
        {page === "Connections" && (
          <Panel className="account-preferences">
            <PanelTitle
              title="Make yourself comfortable"
              note="A quieter experience, whenever you need it."
            />
            <label className="toggle-label">
              <input
                type="checkbox"
                checked={reduced}
                onChange={(e) => setReduced(e.target.checked)}
              />
              <span>Reduce motion</span>
            </label>
            {session && !session.demo && (
              <button
                className="button"
                onClick={async () => {
                  try {
                    await post("/auth/session/logout");
                    conversation.reset();
                    data.reset();
                  } catch {
                    data.notify("Couldn't sign out. Please try again.");
                  }
                }}
              >
                Sign out
              </button>
            )}
            <button className="button" onClick={() => setHistoryOpen(true)}>
              <History size={16} />
              Conversation history
            </button>
            <button
              className="text-button"
              onClick={async () => {
                try {
                  await api("/ops/status");
                  data.notify(
                    "BioTwin is reachable. Connection details are shown above.",
                  );
                } catch {
                  data.notify("BioTwin couldn't be reached. Please reconnect.");
                }
              }}
            >
              Check connection
            </button>
          </Panel>
        )}
        <footer className="app-footer">
          <span>
            <Leaf size={13} />A little more in tune.
          </span>
          <span>Wellness estimates · For your everyday rhythm</span>
        </footer>
      </main>
      <nav className="mobile-tabs" aria-label="Mobile navigation">
        {navButtons}
      </nav>
      {page !== "Overview" && (
        <button className="floating-talk" onClick={talk}>
          <AudioLines size={20} />
          <span>Talk to your twin</span>
        </button>
      )}
      {forecastOpen && (
        <div
          className="modal-backdrop history-backdrop"
          onClick={() => setForecastOpen(false)}
        >
          <section
            className="history-dialog forecast-dialog glass"
            role="dialog"
            aria-modal="true"
            aria-label="Battery Forecast"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-title">
              <div>
                <h2>Battery Forecast</h2>
                <p>Where your fitted model expects this to go</p>
              </div>
              <Radio size={18} className="green" />
            </div>
            {data.trajectory?.available ? (
              <>
                <div className="forecast-chart">
                  <TrajectoryChart
                    measured={data.trajectory.measured}
                    points={data.trajectory.points}
                    referenceLabel={
                      data.trajectory.basis === "replay" ? "last sync" : "now"
                    }
                  />
                </div>
                <div className="signal-stats">
                  {data.trajectory.points.map((p) => (
                    <div key={p.horizon_minutes}>
                      <small>
                        {data.trajectory?.available && data.trajectory.basis === "replay"
                          ? `${p.horizon_minutes / 60}h after sync`
                          : `In ${p.horizon_minutes / 60}h`}
                      </small>
                      <b>{value(p.value)}</b>
                      <small>
                        &plusmn; {value(p.validation_mae, 1)} ·{" "}
                        {p.method === "ridge"
                          ? "ridge model"
                          : p.method === "trend_plus_clock"
                            ? "trend + your rhythm"
                            : "your daily rhythm"}
                      </small>
                    </div>
                  ))}
                </div>
                {/* Which predictor answered, and why -- said once, where
                    someone reading the chart will see it. */}
                <small className="setup-note">
                  {data.trajectory.basis === "model"
                    ? "Solid is measured, dashed is predicted. The ridge model fitted in MATLAB wins at one hour: 1.9 against 2.4 for the best simple rule. Past that your own hour-of-day rhythm predicts better than anything fitted here, so the later points come from it and the band widens to match."
                    : data.trajectory.reason}{" "}
                  Predicts Garmin&rsquo;s Body Battery, not clinically validated.
                </small>
                <small className="setup-note">
                  Model: {data.trajectory.model}. Anchor:{" "}
                  {new Date(data.trajectory.anchor_time).toLocaleString()}.
                </small>
                {data.trajectory.imputed_inputs.length > 0 && (
                  <small className="setup-note">
                    {data.trajectory.imputed_inputs.length} model input
                    unavailable, filled with its training average:{" "}
                    {data.trajectory.imputed_inputs.join(", ")}
                  </small>
                )}
                {daySimulation && activeScenario && (
                  <div className="simulate-day">
                    <div className="simulate-heading">
                      <div>
                        <span className="eyebrow">SIMULATE MY DAY</span>
                        <h3>Move the day. Watch the future change.</h3>
                      </div>
                      <span className="pill green">
                        {daySimulation.basis === "model"
                          ? "Model + rhythm"
                          : "Rhythm estimate"}
                      </span>
                    </div>
                    <div className="scenario-rail" aria-label="Choose a scenario">
                      {daySimulation.scenarios
                        .filter((s) => s.id !== "current_plan")
                        .map((scenario) => (
                          <button
                            key={scenario.id}
                            className={
                              activeScenario.id === scenario.id ? "selected" : ""
                            }
                            onClick={() => setScenarioId(scenario.id)}
                          >
                            <b>{scenario.label}</b>
                            <small>{scenario.summary}</small>
                          </button>
                        ))}
                    </div>
                    {activeScenario.id === "extra_steps" && (
                      <label className="steps-control">
                        <span>
                          Additional activity <b>+{daySteps.toLocaleString()} steps</b>
                        </span>
                        <input
                          type="range"
                          min={daySimulation.controls.step_min}
                          max={daySimulation.controls.step_max}
                          step={500}
                          value={daySteps}
                          onChange={(e) => {
                            const next = Number(e.target.value);
                            setDaySteps(next);
                            void data.simulateDay(next);
                          }}
                        />
                      </label>
                    )}
                    <div className="simulate-visual">
                      <SimulateDayChart
                        baseline={daySimulation.baseline}
                        scenario={activeScenario}
                      />
                    </div>
                    <div className="simulate-decisions">
                      {[
                        ["Best window", activeScenario.decision.best_window],
                        ["Workout", activeScenario.decision.workout],
                        [
                          "Evening state",
                          `${value(activeScenario.decision.evening_state, 1)}%`,
                        ],
                        ["Activity load", activeScenario.decision.activity_load],
                      ].map(([label, metric]) => (
                        <div key={label}>
                          <small>{label}</small>
                          <b>{metric}</b>
                        </div>
                      ))}
                    </div>
                    <p className="coach-readout">{daySimulation.coach_summary}</p>
                    <small className="setup-note">
                      {daySimulation.assumptions.join(" ")}
                    </small>
                  </div>
                )}
              </>
            ) : (
              <div className="empty-state">
                <Radio size={22} />
                <p>
                  {data.trajectory?.reason ??
                    "Waiting for a Body Battery reading from your watch."}
                </p>
              </div>
            )}
            <button className="primary" onClick={() => setForecastOpen(false)}>
              Close
            </button>
          </section>
        </div>
      )}
      {historyOpen && (
        <div
          className="modal-backdrop history-backdrop"
          onClick={() => setHistoryOpen(false)}
        >
          <section
            ref={transcript}
            className="history-dialog glass"
            role="dialog"
            aria-modal="true"
            aria-label="Conversation history"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-title">
              <div>
                <span className="eyebrow">YOU & YOUR TWIN</span>
                <h2>Conversations</h2>
              </div>
              <button
                className="icon-btn"
                aria-label="Close conversation history"
                onClick={() => setHistoryOpen(false)}
              >
                <X size={20} />
              </button>
            </div>
            <div className="history-scroll">
              {conversation.historyBusy && (
                <p role="status">Loading your conversations…</p>
              )}
              {conversation.historyError && (
                <p role="alert">{conversation.historyError}</p>
              )}
              {conversation.nextBefore && (
                <button
                  className="button"
                  disabled={conversation.historyBusy}
                  onClick={() =>
                    conversation.loadHistory(conversation.nextBefore!)
                  }
                >
                  Earlier conversations
                </button>
              )}
              {!conversation.messages.length && (
                <div className="empty-state">
                  <History size={30} />
                  <h3>A little clarity, saved.</h3>
                  <p>
                    Your questions and your twin's answers will appear here.
                  </p>
                </div>
              )}
              {conversation.messages.map((m) => (
                <article className={`transcript-message ${m.role}`} key={m.key}>
                  <div>
                    <b>{m.role === "user" ? "You" : "Your twin"}</b>
                    <time dateTime={m.created_at}>
                      {new Date(m.created_at).toLocaleString(undefined, {
                        month: "short",
                        day: "numeric",
                        hour: "numeric",
                        minute: "2-digit",
                      })}
                    </time>
                  </div>
                  <p>{m.text}</p>
                  {m.reply?.notice && (
                    <p className="fine-print">{m.reply.notice}</p>
                  )}
                  {m.reply && (
                    <button
                      className="text-button"
                      onClick={() => {
                        autoTopic.current = false;
                        void conversation.speak(m.reply!);
                      }}
                    >
                      <Volume2 size={14} />
                      Listen again
                    </button>
                  )}
                </article>
              ))}
            </div>
            {voiceControls}
            <button
              className="button primary"
              onClick={() => {
                setHistoryOpen(false);
                talk();
              }}
            >
              Ask something new
              <ArrowUpRight size={15} />
            </button>
          </section>
        </div>
      )}
      {auth && (
        <AuthModal
          onClose={() => setAuth(false)}
          onDone={() => {
            conversation.reset();
            data.reset();
          }}
        />
      )}
      {data.notice && (
        <div className="toast" role="status">
          <Check size={17} />
          <span>{data.notice}</span>
          <button
            className="icon-btn"
            aria-label="Dismiss notification"
            onClick={() => data.notify("")}
          >
            <X size={16} />
          </button>
        </div>
      )}
    </div>
  );
}
