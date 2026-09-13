import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowLeft,
  ArrowUpRight,
  AudioLines,
  CalendarDays,
  Check,
  ChevronRight,
  FlaskConical,
  History,
  LayoutGrid,
  Leaf,
  Link2,
  LoaderCircle,
  Mic,
  Pause,
  Send,
  Sparkles,
  Volume2,
  X,
} from "lucide-react";
import Avatar from "./Avatar";
import Connections, { AuthModal } from "./Connections";
import { api, post } from "./api";
import { useDashboard } from "./useDashboard";
import { useTwinConversation } from "./useTwinConversation";
import { questionScenario, questionTopic, type Topic } from "./topics";
import {
  CalendarDay,
  LabPanel,
  Metric,
  Panel,
  PanelTitle,
  PlanPanel,
  Range,
  ReadinessDetails,
  ReadinessPanel,
  RecoveryPanel,
  SignalDetail,
  signalDefinitions,
  topicSignal,
} from "./DashboardPanels";
import type { CaptionWord } from "./captions";
import type { SimulationOverlay } from "./contracts";

type Page =
  "Overview" | "Signals" | "Daily plan" | "What-if lab" | "Connections";
const navigation = [
  { name: "Overview", icon: LayoutGrid },
  { name: "Signals", icon: Activity },
  { name: "Daily plan", icon: CalendarDays },
  { name: "What-if lab", icon: FlaskConical },
  { name: "Connections", icon: Link2 },
] as const;
const descriptions: Record<Page, string> = {
  Overview: "A little awareness. A better day.",
  Signals: "The small signals that tell your story.",
  "Daily plan": "A little space for what you need.",
  "What-if lab": "See what a change of pace could look like.",
  Connections: "Your watch, your schedule, your rhythm.",
};
const topicTitles: Record<Topic, string> = {
  heart: "A closer look at your heart",
  sleep: "Let's talk about sleep",
  calories: "Your energy in motion",
  steps: "Every step adds up",
  plan: "Let's find your window",
  "what-if": "Let's explore that possibility",
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
  const [page, setPage] = useState<Page>("Overview");
  const [auth, setAuth] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
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
  const [mobile, setMobile] = useState(
    () => matchMedia("(max-width: 760px)").matches,
  );
  const input = useRef<HTMLInputElement>(null);
  const transcript = useRef<HTMLDivElement>(null);
  const noOverlay = useRef<SimulationOverlay | null>(null);
  const autoTopic = useRef(false);
  const conversation = useTwinConversation({
    open: true,
    online: status === "online",
    bundle: data.bundle,
    session,
    accountKey: data.accountKey,
    onQuestion: (text) => {
      const topic = questionTopic(text);
      setPage("Overview");
      setHistoryOpen(false);
      autoTopic.current = !!topic;
      data.clearSimulation();
      setTakeover(topic ? { topic, question: text, automatic: true } : null);
      if (topic === "what-if") void data.simulate(questionScenario(text));
      window.scrollTo({ top: 0, behavior: "instant" });
    },
    onSpeechEnd: () => {
      if (autoTopic.current) {
        autoTopic.current = false;
        setTakeover(null);
        setPage("Overview");
        data.clearSimulation();
        window.scrollTo({ top: 0, behavior: "instant" });
      }
    },
  });
  const { speaking, listening, asking, transcribing } = conversation;
  const phase = listening
    ? "Listening"
    : transcribing
      ? "Transcribing"
      : asking
        ? "Thinking"
        : speaking
          ? "Speaking"
          : "Here with you";
  useEffect(() => {
    const query = matchMedia("(max-width: 760px)");
    const update = () => setMobile(query.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);
  useEffect(() => {
    setAdded([]);
    setTakeover(null);
    autoTopic.current = false;
  }, [data.accountKey]);
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
    data.clearSimulation();
    window.scrollTo({ top: 0, behavior: "instant" });
  }
  function dismiss() {
    autoTopic.current = false;
    setTakeover(null);
    data.clearSimulation();
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
  const demo = status === "offline" || session?.demo;
  const battery = state?.energy_reserve_pct;
  const recentReply = conversation.messages
    .filter((m) => m.role === "twin")
    .at(-1);
  const answer = recentReply?.text ?? "";
  const talk = () => {
    navigate("Overview");
    requestAnimationFrame(() => input.current?.focus());
  };
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
          <div className="nav-note">
            <span className="green">
              <Sparkles size={19} />
            </span>
            <p>
              A little more in tune
              <br />
              with yourself.
            </p>
            <button onClick={talk}>
              Talk to your twin <ArrowUpRight size={15} />
            </button>
          </div>
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
                  : "Your personal twin"}
              </b>
              <small>
                {session?.demo ? "Make it yours" : "Account & preferences"}
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
        <div className="bar-location">
          <span>MY BIOTWIN</span>
          <b>{page}</b>
        </div>
        <div
          className="body-battery"
          title="BioTwin estimate: 80% readiness plus 20% live heart-rate recovery when available. Readiness includes sleep, HRV, resting pattern and sleep debt. Not Garmin’s score."
          aria-label={`Body Battery ${battery == null ? "awaiting data" : battery + " percent"}`}
        >
          <div>
            <b>Body Battery</b>
            <small>
              {status === "offline" ? "Offline example" : "Energy estimate"}
            </small>
          </div>
          <div
            className={`battery-cell ${battery != null && battery < 30 ? "low" : ""}`}
            role="meter"
            aria-label="Body Battery estimate"
            aria-valuemin={0}
            aria-valuemax={100}
            aria-valuenow={battery ?? undefined}
          >
            <span style={{ width: `${battery ?? 0}%` }} />
            <b>{battery == null ? "—" : `${battery}%`}</b>
          </div>
        </div>
        <button
          className={`bar-twin ${speaking || listening ? "active" : ""}`}
          onClick={talk}
          aria-label={`Twin ${phase}`}
        >
          <AudioLines size={18} />
          <span>{phase}</span>
        </button>
        <button
          className="icon-btn history-launch"
          aria-label="Conversation history"
          onClick={() => setHistoryOpen(true)}
        >
          <History size={20} />
        </button>
      </header>
      <main className="workspace" id="main-content">
        <div className="page-intro">
          <div>
            <span className="eyebrow">
              {new Date().toLocaleDateString(undefined, {
                weekday: "long",
                month: "long",
                day: "numeric",
              })}
            </span>
            <h1>
              {page === "Overview"
                ? `Your daily rhythm${session && !session.demo && session.user.name ? ", " + session.user.name.split(" ")[0] : ""}.`
                : page}
            </h1>
            <p>{descriptions[page]}</p>
          </div>
          <span className={`connection-pill ${status}`}>
            <i />
            {status === "offline"
              ? "Offline example"
              : status === "connecting"
                ? "Connecting"
                : demo
                  ? "Preview workspace"
                  : "Connected"}
          </span>
        </div>
        {status === "offline" && (
          <div className="notice offline-notice" role="status">
            You're viewing an offline example. Your personal measurements aren't
            updating.<button onClick={data.reset}>Reconnect</button>
          </div>
        )}
        {demo && status === "online" && (
          <div className="preview-note">
            <span>
              {state?.provenance_banner === "synthetic"
                ? "Explore with example measurements."
                : "Previewing shared wearable measurements."}
            </span>
            <button onClick={() => setAuth(true)}>
              Connect your own data <ArrowUpRight size={13} />
            </button>
          </div>
        )}
        {!state && (
          <div className="loading-screen">
            <LoaderCircle size={24} className="spin" />
            <p>Getting your twin ready…</p>
          </div>
        )}
        {state && (page === "Overview" || page === "What-if lab") && (
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
                In sync
                <br />
                <em>with you.</em>
              </h2>
              <p>
                Your signals, brought to life.
                <br />
                Ask your twin what's on your mind.
              </p>
              <span className="hero-state">
                <span className="status-dot" />
                {phase}
              </span>
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
              <Avatar
                live={data.live}
                overlay={
                  page === "What-if lab" || takeover?.topic === "what-if"
                    ? data.overlay
                    : noOverlay
                }
                state={state}
                reduced={reduced}
                speaking={speaking}
                listening={listening}
                thinking={asking}
                compact={mobile || !!takeover}
              />
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
              <span className="composer-hint">
                {listening
                  ? "Listening · tap to finish"
                  : transcribing
                    ? "Turning your voice into words…"
                    : "Made personal by your data"}
                <button onClick={() => setHistoryOpen(true)}>
                  <History size={13} />
                  History
                </button>
              </span>
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
                    <PlanPanel data={data} actions={actions} />
                    <CalendarDay data={data} />
                  </>
                ) : takeover.topic === "what-if" ? (
                  <LabPanel data={data} />
                ) : (
                  <>
                    <ReadinessPanel data={data} />
                    <RecoveryPanel data={data} />
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
              <div className="section-label">
                <h2>Your essentials</h2>
                <button onClick={() => navigate("Signals")}>
                  All signals <ArrowUpRight size={14} />
                </button>
              </div>
              <div className="essentials-grid">
                {signalDefinitions.slice(0, 4).map((m, i) => (
                  <Metric
                    key={m.field}
                    field={m.field}
                    data={data}
                    onClick={() =>
                      explore(
                        (["heart", "sleep", "calories", "steps"] as Topic[])[i],
                      )
                    }
                  />
                ))}
              </div>
              <div className="overview-insights">
                <ReadinessPanel data={data} />
                <RecoveryPanel data={data} />
              </div>
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
              {signalDefinitions.map((m) => (
                <Panel key={m.field}>
                  <SignalDetail field={m.field} data={data} />
                </Panel>
              ))}
            </div>
            <ReadinessDetails data={data} />
          </>
        )}
        {state && page === "Daily plan" && (
          <>
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
        {state && page === "What-if lab" && (
          <>
            <div className="lab-layout">
              <LabPanel data={data} />
              <Panel className="lab-context">
                <FlaskConical size={28} className="blue" />
                <h2>
                  Possibilities,
                  <br />
                  not promises.
                </h2>
                <p>
                  Scenarios help you explore a change of pace. They use
                  assumptions, and aren't a prediction of an intervention's
                  effect on your health.
                </p>
                <ReadinessDetails data={data} />
              </Panel>
            </div>
          </>
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
      {page !== "Overview" && page !== "What-if lab" && (
        <button className="floating-talk" onClick={talk}>
          <AudioLines size={20} />
          <span>Talk to your twin</span>
        </button>
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
