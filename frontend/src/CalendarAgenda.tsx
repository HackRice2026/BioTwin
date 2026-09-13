import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type FormEvent,
} from "react";
import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  Plus,
  Search,
  MapPin,
  ExternalLink,
  CheckCircle2,
  Circle,
  Repeat2,
  Sparkles,
  X,
  Send,
} from "lucide-react";
import { post } from "./api";
import {
  dayInZone,
  shiftDay,
  type CalendarData,
  type CalendarDraft,
  type CalendarEvent,
} from "./useCalendar";
import { Panel, PanelTitle } from "./DashboardPanels";

const displayDate = (
  day: string,
  options: Intl.DateTimeFormatOptions = { month: "long", day: "numeric" },
) =>
  new Date(`${day}T12:00:00Z`).toLocaleDateString(undefined, {
    ...options,
    timeZone: "UTC",
  });
const clockTime = (s: string, timezone: string) =>
  new Date(s).toLocaleTimeString(undefined, {
    hour: "numeric",
    minute: "2-digit",
    timeZone: timezone,
  });
const color = (s: string) => (/^#[0-9a-f]{6}$/i.test(s) ? s : "#8bc5a6");
const dateOf = (event: CalendarEvent, tz: string) =>
  event.all_day ? event.start.slice(0, 10) : dayInZone(event.start, tz);

export function CalendarAgenda({
  calendar,
  onConnect,
  onNew,
  onAsk,
  asking,
  compact = false,
}: {
  calendar: CalendarData;
  onConnect: () => void;
  onNew: () => void;
  onAsk: (question: string) => void;
  asking: boolean;
  compact?: boolean;
}) {
  const { agenda, start, days, loading, error, timezone } = calendar;
  const [search, setSearch] = useState("");
  const [source, setSource] = useState("all");
  const [selected, setSelected] = useState<string | null>(null);
  const [taskStatus, setTaskStatus] = useState("open");
  const [question, setQuestion] = useState("");
  useEffect(() => {
    setSelected(null);
  }, [start, days]);
  const events = (agenda?.events ?? []).filter(
    (e) =>
      (source === "all" || e.calendar_id === source) &&
      `${e.title} ${e.location ?? ""} ${e.calendar_name}`
        .toLowerCase()
        .includes(search.toLowerCase()) &&
      (!selected ||
        (dateOf(e, timezone) <= selected &&
          (e.all_day
            ? e.end.slice(0, 10) > selected
            : dayInZone(e.end, timezone) >= selected))),
  );
  const groups = useMemo(() => {
    const result = new Map<string, CalendarEvent[]>();
    for (const e of events) {
      const day =
        selected ?? (dateOf(e, timezone) < start ? start : dateOf(e, timezone));
      result.set(day, [...(result.get(day) ?? []), e]);
    }
    return [...result.entries()].sort(([a], [b]) => a.localeCompare(b));
  }, [events, selected, timezone, start]);
  const tasks = (agenda?.tasks ?? []).filter(
    (t) =>
      (!t.due || (t.due >= start && t.due < calendar.end)) &&
      (taskStatus === "all" ||
        (taskStatus === "done" ? t.completed : !t.completed)) &&
      `${t.title} ${t.list_name}`.toLowerCase().includes(search.toLowerCase()),
  );
  const connected =
    agenda && ["connected", "partial", "demo"].includes(agenda.status);
  const canWrite = agenda?.calendars.some(
    (c) => c.provider === "google-calendar" && c.writable,
  );
  return (
    <Panel className={`calendar-agenda ${compact ? "compact-agenda" : ""}`}>
      <div className="calendar-heading">
        <div>
          <span className="eyebrow">YOUR TIME, TOGETHER</span>
          <h2>Your calendar</h2>
          <p>
            {timezone} <span>·</span>{" "}
            {agenda?.status === "demo" ? "Example schedule" : "Events & tasks"}
          </p>
        </div>
        <div className="calendar-heading-actions">
          <button
            className="icon-button"
            aria-label="Refresh calendar events"
            disabled={loading || !calendar.online}
            onClick={() => void calendar.refresh()}
          >
            <RefreshCw size={17} className={loading ? "spin" : ""} />
          </button>
          <button
            className="button primary"
            onClick={canWrite ? onNew : onConnect}
          >
            <Plus size={16} /> New event
          </button>
        </div>
      </div>
      {!calendar.online ? (
        <div className="empty-state">
          <CalendarDays />
          <h3>Your calendar needs a connection</h3>
          <p>Reconnect to view your private events and tasks.</p>
        </div>
      ) : (
        <>
          <div className="calendar-toolbar">
            <div className="calendar-period">
              <button
                className="icon-button"
                aria-label="Previous calendar range"
                onClick={() => calendar.setStart(shiftDay(start, -days))}
              >
                <ChevronLeft size={18} />
              </button>
              <button
                className="text-button"
                onClick={() =>
                  calendar.setStart(dayInZone(new Date(), timezone))
                }
              >
                Today
              </button>
              <button
                className="icon-button"
                aria-label="Next calendar range"
                onClick={() => calendar.setStart(shiftDay(start, days))}
              >
                <ChevronRight size={18} />
              </button>
              <label className="calendar-date-picker">
                <span className="sr-only">Calendar start date</span>
                <input
                  aria-label="Calendar start date"
                  type="date"
                  value={start}
                  onChange={(e) =>
                    e.target.value && calendar.setStart(e.target.value)
                  }
                />
              </label>
            </div>
            <select
              aria-label="Calendar date range"
              value={days}
              onChange={(e) => calendar.setDays(Number(e.target.value))}
            >
              <option value={7}>7 days</option>
              <option value={30}>30 days</option>
            </select>
          </div>
          <div className="calendar-range-label">
            {displayDate(start)} —{" "}
            {displayDate(shiftDay(calendar.end, -1), {
              month: "long",
              day: "numeric",
              year: "numeric",
            })}
          </div>
          {days === 7 && (
            <div
              className="calendar-week"
              role="group"
              aria-label="Filter calendar by day"
            >
              {Array.from({ length: days }, (_, i) => shiftDay(start, i)).map(
                (day) => {
                  const count = (agenda?.events ?? []).filter(
                    (e) => dateOf(e, timezone) === day,
                  ).length;
                  return (
                    <button
                      key={day}
                      className={`${selected === day ? "selected" : ""} ${day === dayInZone(new Date(), timezone) ? "today" : ""}`}
                      aria-label={`Show ${day}`}
                      aria-pressed={selected === day}
                      onClick={() => setSelected(selected === day ? null : day)}
                    >
                      <small>{displayDate(day, { weekday: "short" })}</small>
                      <b>{day.slice(-2)}</b>
                      <span>
                        {count ? "•".repeat(Math.min(count, 3)) : "·"}
                      </span>
                    </button>
                  );
                },
              )}
            </div>
          )}
          <div className="calendar-filters">
            <label className="calendar-search">
              <Search size={16} />
              <input
                aria-label="Search events and tasks"
                placeholder="Search events or tasks"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </label>
            <select
              aria-label="Filter calendar"
              value={source}
              onChange={(e) => setSource(e.target.value)}
            >
              <option value="all">All calendars</option>
              {agenda?.calendars.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
          {selected && (
            <button className="text-button" onClick={() => setSelected(null)}>
              Show all days
            </button>
          )}
          {error && (
            <p className="calendar-notice" role="alert">
              {error}{" "}
              <button onClick={() => void calendar.refresh()}>Try again</button>
            </p>
          )}
          {agenda?.warnings.map((w) => (
            <p className="calendar-notice" key={w}>
              {w} <button onClick={onConnect}>Connections</button>
            </p>
          ))}
          {loading && !agenda && (
            <p role="status" className="calendar-loading">
              Loading your calendar…
            </p>
          )}
          {!loading && !error && !connected && (
            <div className="empty-state">
              <CalendarDays size={28} />
              <h3>Make room for your whole day.</h3>
              <p>
                Connect Google Calendar to see your events here and plan with
                your twin.
              </p>
              <button className="button primary" onClick={onConnect}>
                Connect your calendar
              </button>
            </div>
          )}
          {connected && (
            <>
              <div className="calendar-count">
                <h3>
                  {events.length} {events.length === 1 ? "event" : "events"}
                </h3>
                <span>
                  {loading
                    ? "Refreshing…"
                    : agenda?.status === "partial"
                      ? "Some calendars unavailable"
                      : "All matching events shown"}
                </span>
              </div>
              <div className="calendar-event-list">
                {groups.map(([day, rows]) => (
                  <section key={day} className="calendar-day-group">
                    <h4>
                      {displayDate(day, {
                        weekday: "long",
                        month: "short",
                        day: "numeric",
                      })}
                      {day === dayInZone(new Date(), timezone) && (
                        <span>Today</span>
                      )}
                    </h4>
                    {rows.map((e) => (
                      <details
                        key={e.id}
                        className="calendar-event"
                        style={
                          { "--event-color": color(e.color) } as CSSProperties
                        }
                      >
                        <summary>
                          <div className="event-clock">
                            <b>
                              {e.all_day
                                ? "All day"
                                : clockTime(e.start, timezone)}
                            </b>
                            <small>
                              {e.all_day
                                ? e.end.slice(0, 10) !==
                                  shiftDay(e.start.slice(0, 10), 1)
                                  ? `through ${displayDate(shiftDay(e.end.slice(0, 10), -1))}`
                                  : ""
                                : clockTime(e.end, timezone)}
                            </small>
                          </div>
                          <i className="event-color" />
                          <div className="event-summary">
                            <h5>{e.title}</h5>
                            <p>
                              <span className="calendar-source-dot" />
                              {e.calendar_name}
                              {e.recurring && (
                                <Repeat2
                                  size={12}
                                  aria-label="Recurring event"
                                />
                              )}
                            </p>
                            {e.location && (
                              <small>
                                <MapPin size={12} />
                                {e.location}
                              </small>
                            )}
                          </div>
                          <ChevronRight size={16} className="event-chevron" />
                        </summary>
                        <div className="event-details">
                          <p>
                            {e.all_day
                              ? `All day · ${e.start.slice(0, 10)} to ${shiftDay(e.end.slice(0, 10), -1)}`
                              : `${new Date(e.start).toLocaleString(undefined, { timeZone: timezone })} – ${new Date(e.end).toLocaleString(undefined, { timeZone: timezone })}`}{" "}
                            · {timezone}
                          </p>
                          {e.description && (
                            <p className="event-description">{e.description}</p>
                          )}
                          {e.url && (
                            <a href={e.url} target="_blank" rel="noreferrer">
                              Open in calendar <ExternalLink size={13} />
                            </a>
                          )}
                        </div>
                      </details>
                    ))}
                  </section>
                ))}
                {!events.length && (
                  <div className="calendar-empty">
                    <CalendarDays size={24} />
                    <p>
                      {search || source !== "all"
                        ? "No events match these filters."
                        : agenda?.status === "partial"
                          ? "No events were returned. Some calendars could not refresh."
                          : "No events in this range. A little breathing room."}
                    </p>
                  </div>
                )}
              </div>
              <div className="calendar-tasks">
                <div className="calendar-count">
                  <h3>
                    Tasks <span>{tasks.length}</span>
                  </h3>
                  <select
                    aria-label="Filter tasks"
                    value={taskStatus}
                    onChange={(e) => setTaskStatus(e.target.value)}
                  >
                    <option value="open">Open tasks</option>
                    <option value="done">Completed</option>
                    <option value="all">All tasks</option>
                  </select>
                </div>
                {tasks.map((t) => (
                  <details
                    key={t.id}
                    className={`calendar-task ${t.completed ? "completed" : ""}`}
                  >
                    <summary>
                      {t.completed ? (
                        <CheckCircle2 size={18} />
                      ) : (
                        <Circle size={18} />
                      )}
                      <div>
                        <b>{t.title}</b>
                        <small>
                          {t.list_name} ·{" "}
                          {t.due ? `Due ${displayDate(t.due)}` : "No due date"}
                        </small>
                      </div>
                    </summary>
                    <p>{t.notes || "No additional notes."}</p>
                    {t.url && (
                      <a href={t.url} target="_blank" rel="noreferrer">
                        Open task <ExternalLink size={13} />
                      </a>
                    )}
                  </details>
                ))}
                {!tasks.length && (
                  <p className="fine-print">
                    {agenda?.tasks_status === "unavailable"
                      ? "Grant Google Tasks access in Connections to see your task lists."
                      : agenda?.status === "demo"
                        ? "Connect your account to see your tasks."
                        : "No matching tasks. Undated tasks appear here too."}
                  </p>
                )}
              </div>
              <form
                className="calendar-ask"
                onSubmit={(e) => {
                  e.preventDefault();
                  if (question.trim()) {
                    onAsk(question);
                    setQuestion("");
                  }
                }}
              >
                <Sparkles size={19} />
                <label>
                  <span>Plan with your twin</span>
                  <input
                    aria-label="Ask about your calendar"
                    placeholder="What’s on my calendar? Or add an event…"
                    value={question}
                    onChange={(e) => setQuestion(e.target.value)}
                    maxLength={1000}
                  />
                </label>
                <button
                  className="icon-button"
                  type="submit"
                  aria-label="Ask calendar question"
                  disabled={asking || !question.trim()}
                >
                  <Send size={17} />
                </button>
              </form>
            </>
          )}
        </>
      )}
    </Panel>
  );
}

function localInput(value: string, timezone: string) {
  const d = new Date(value);
  const parts = new Intl.DateTimeFormat("sv-SE", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
  }).format(d);
  return parts.replace(" ", "T");
}
export function CalendarEditor({
  draft,
  calendar,
  onClose,
  onAdded,
}: {
  draft: CalendarDraft | "new";
  calendar: CalendarData;
  onClose: () => void;
  onAdded: (start: string) => void;
}) {
  const initial = draft === "new" ? null : draft;
  const tz = initial?.timezone || calendar.timezone;
  const writable =
    calendar.agenda?.calendars.filter(
      (c) => c.provider === "google-calendar" && c.writable,
    ) ?? [];
  const [title, setTitle] = useState(initial?.title || "");
  const [allDay, setAllDay] = useState(initial?.all_day || false);
  const [start, setStart] = useState(
    initial
      ? initial.all_day
        ? initial.start
        : localInput(initial.start, tz)
      : `${calendar.start}T09:00`,
  );
  const [end, setEnd] = useState(
    initial
      ? initial.all_day
        ? initial.end
        : localInput(initial.end, tz)
      : `${calendar.start}T09:30`,
  );
  const [target, setTarget] = useState(
    initial?.calendar_id ||
      writable.find((c) => c.primary)?.id ||
      writable[0]?.id ||
      "primary",
  );
  const [location, setLocation] = useState(initial?.location || "");
  const [notes, setNotes] = useState(initial?.notes || "");
  const [reminder, setReminder] = useState(initial?.reminder_minutes ?? 10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const saved = useRef<{ signature: string; id: string } | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement | null;
    dialog.current?.querySelector<HTMLInputElement>("input")?.focus();
    const key = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !busy) onClose();
      if (e.key !== "Tab") return;
      const controls = [
        ...(dialog.current?.querySelectorAll<HTMLElement>(
          "button:not(:disabled), input, select, textarea, a[href]",
        ) ?? []),
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
    };
    document.addEventListener("keydown", key);
    return () => {
      document.removeEventListener("keydown", key);
      previous?.focus();
    };
  }, [busy]);
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const body = {
        title,
        start,
        end,
        all_day: allDay,
        calendar_id: target,
        location,
        notes,
        reminder_minutes: reminder,
      };
      const signature = JSON.stringify(body);
      if (saved.current?.signature !== signature) {
        const next = await post<CalendarDraft>("/api/calendar/drafts", body);
        saved.current = { signature, id: next.id };
      }
      await post(`/api/calendar/drafts/${saved.current!.id}/confirm`);
      onAdded(start.slice(0, 10));
    } catch (e) {
      setError(
        (e as Error).message ||
          "Your event could not be added. Please try again.",
      );
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="modal-backdrop">
      <div
        className="modal calendar-editor"
        role="dialog"
        aria-modal="true"
        aria-label="Review calendar event"
        ref={dialog}
      >
        <button
          className="icon-button modal-close"
          aria-label="Close event editor"
          disabled={busy}
          onClick={onClose}
        >
          <X size={18} />
        </button>
        <PanelTitle
          title={initial ? "A little room, planned." : "New event"}
          note={`Review before adding · ${tz}`}
        />
        <form onSubmit={submit}>
          <label>
            Event title
            <input
              aria-label="Event title"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              maxLength={200}
              required
            />
          </label>
          <label>
            Calendar
            <select
              aria-label="Event calendar"
              value={target}
              onChange={(e) => setTarget(e.target.value)}
            >
              {writable.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
              {!writable.length && initial && (
                <option value={initial.calendar_id}>
                  {initial.calendar_name}
                </option>
              )}
            </select>
          </label>
          <label className="calendar-all-day">
            <input
              type="checkbox"
              checked={allDay}
              onChange={(e) => {
                setAllDay(e.target.checked);
                setStart(
                  e.target.checked
                    ? start.slice(0, 10)
                    : `${start.slice(0, 10)}T09:00`,
                );
                setEnd(
                  e.target.checked
                    ? shiftDay(start.slice(0, 10), 1)
                    : `${start.slice(0, 10)}T09:30`,
                );
              }}
            />
            All day
          </label>
          <div className="calendar-editor-times">
            <label>
              Starts
              <input
                aria-label="Event start"
                type={allDay ? "date" : "datetime-local"}
                value={start}
                onChange={(e) => setStart(e.target.value)}
                required
              />
            </label>
            <label>
              {allDay ? "End date (not included)" : "Ends"}
              <input
                aria-label="Event end"
                type={allDay ? "date" : "datetime-local"}
                value={end}
                onChange={(e) => setEnd(e.target.value)}
                required
              />
            </label>
          </div>
          <label>
            Location
            <input
              aria-label="Event location"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              maxLength={500}
              placeholder="Optional"
            />
          </label>
          <label>
            Notes
            <textarea
              aria-label="Event notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              maxLength={2000}
              placeholder="Anything to remember"
              rows={2}
            />
          </label>
          <label>
            Remind me
            <select
              aria-label="Event reminder"
              value={reminder}
              onChange={(e) => setReminder(Number(e.target.value))}
            >
              {[0, 5, 10, 15, 30, 60, 1440].map((m) => (
                <option key={m} value={m}>
                  {m === 0
                    ? "At the event"
                    : m === 1440
                      ? "1 day before"
                      : `${m} minutes before`}
                </option>
              ))}
              {![0, 5, 10, 15, 30, 60, 1440].includes(reminder) && (
                <option value={reminder}>{reminder} minutes before</option>
              )}
            </select>
          </label>
          {error && (
            <p className="calendar-notice" role="alert">
              {error}
            </p>
          )}
          <p className="fine-print">
            Your event is added only when you confirm below. We check the
            selected calendar for overlapping events.
          </p>
          <button className="button primary" type="submit" disabled={busy}>
            {busy ? "Adding…" : "Add to calendar"}
            <CalendarDays size={16} />
          </button>
        </form>
      </div>
    </div>
  );
}
