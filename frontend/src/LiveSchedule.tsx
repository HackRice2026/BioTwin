import { useEffect, useRef, useState } from "react";
import { CalendarCheck, CheckCircle2, X } from "lucide-react";
import type { DailyPlan, Proposal } from "./contracts";

const WINDOW_START_HOUR = 6;
const WINDOW_END_HOUR = 23;
const WINDOW_HOURS = WINDOW_END_HOUR - WINDOW_START_HOUR;

function pct(d: Date) {
  const hours = d.getHours() + d.getMinutes() / 60;
  return Math.min(100, Math.max(0, ((hours - WINDOW_START_HOUR) / WINDOW_HOURS) * 100));
}
function clock(d: Date) {
  return d.toLocaleTimeString(undefined, { hour: "numeric", minute: "2-digit" });
}
function speak(text: string) {
  if (!("speechSynthesis" in window)) return;
  window.speechSynthesis.cancel();
  const utter = new SpeechSynthesisUtterance(text);
  utter.rate = 1.02;
  window.speechSynthesis.speak(utter);
}

type Phase = "scanning" | "found" | "empty" | "booking" | "booked" | "declined";

export default function LiveSchedule({
  plan,
  onBook,
  onClose,
}: {
  plan: DailyPlan | null;
  onBook: (proposalId: string) => Promise<void>;
  onClose: () => void;
}) {
  const [phase, setPhase] = useState<Phase>("scanning");
  const best = useRef<Proposal | undefined>(
    plan?.proposals.filter((p) => p.kind === "workout").sort((a, b) => b.score - a.score)[0],
  );

  useEffect(() => {
    speak(
      best.current
        ? "Let me look through your calendar for a good window."
        : "Let me check your calendar.",
    );
    const timer = setTimeout(() => {
      if (best.current) {
        setPhase("found");
        const p = best.current;
        speak(
          `${clock(new Date(p.start))} to ${clock(new Date(p.end))} looks best. ${p.reason} Want me to book it?`,
        );
      } else {
        setPhase("empty");
        speak("I don't see a good window for a workout today. Your calendar is already full, or today isn't a good readiness day for it.");
      }
    }, 1900);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function confirm() {
    if (!best.current) return;
    setPhase("booking");
    try {
      await onBook(best.current.id);
      setPhase("booked");
      speak("Booked it. See you then.");
    } catch (e) {
      setPhase("found");
      speak("That didn't go through. Want to try again?");
    }
  }
  function decline() {
    setPhase("declined");
    speak("No problem, leaving your calendar as is.");
    setTimeout(onClose, 1400);
  }

  const busy = plan?.busy ?? [];
  const p = best.current;

  return (
    <div className="live-schedule-overlay" role="dialog" aria-label="Finding your workout window">
      <div className="live-schedule-card">
        <button className="icon-btn live-schedule-close" aria-label="Close" onClick={onClose}>
          <X size={16} />
        </button>
        <div className="live-schedule-heading">
          <CalendarCheck size={18} />
          <h3>
            {phase === "scanning" && "Scanning your day…"}
            {phase === "found" && "Found a window"}
            {phase === "empty" && "No good window today"}
            {phase === "booking" && "Booking it…"}
            {phase === "booked" && "Booked"}
            {phase === "declined" && "Left as is"}
          </h3>
        </div>

        <div className={`live-timeline ${phase === "scanning" ? "scanning" : ""}`}>
          {phase === "scanning" && <div className="live-timeline-sweep" />}
          {busy.map((b, i) => (
            <div
              key={i}
              className="live-timeline-busy"
              style={{ left: `${pct(new Date(b.start))}%`, width: `${Math.max(1, pct(new Date(b.end)) - pct(new Date(b.start)))}%` }}
              title={b.title}
            />
          ))}
          {p && (phase === "found" || phase === "booking" || phase === "booked") && (
            <div
              className={`live-timeline-proposed ${phase}`}
              style={{ left: `${pct(new Date(p.start))}%`, width: `${Math.max(2, pct(new Date(p.end)) - pct(new Date(p.start)))}%` }}
            >
              {phase === "booked" && <CheckCircle2 size={13} />}
            </div>
          )}
          <div className="live-timeline-hours">
            <span>{WINDOW_START_HOUR}AM</span>
            <span>Noon</span>
            <span>{WINDOW_END_HOUR - 12}PM</span>
          </div>
        </div>

        {phase === "found" && p && (
          <>
            <p className="live-schedule-proposal">
              <b>
                {clock(new Date(p.start))} – {clock(new Date(p.end))}
              </b>
              <span>{p.reason}</span>
            </p>
            <div className="live-schedule-actions">
              <button className="button primary" onClick={confirm}>
                Yes, book it
              </button>
              <button className="button" onClick={decline}>
                Not now
              </button>
            </div>
          </>
        )}
        {phase === "empty" && (
          <div className="live-schedule-actions">
            <button className="button" onClick={onClose}>
              Got it
            </button>
          </div>
        )}
        {phase === "booked" && p && (
          <>
            <p className="live-schedule-proposal">
              <b>
                {clock(new Date(p.start))} – {clock(new Date(p.end))}
              </b>
              <span>On your calendar now.</span>
            </p>
            <div className="live-schedule-actions">
              <button className="button primary" onClick={onClose}>
                Nice
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
