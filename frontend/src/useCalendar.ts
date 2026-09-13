import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Session } from "./api";

export type CalendarEvent = {
  id: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  calendar_id: string;
  calendar_name: string;
  color: string;
  provider: string;
  location?: string;
  description?: string;
  url?: string;
  recurring?: boolean;
};
export type CalendarTask = {
  id: string;
  title: string;
  due: string | null;
  list_name: string;
  completed: boolean;
  notes: string;
  url?: string;
};
export type CalendarSource = {
  id: string;
  name: string;
  color: string;
  primary: boolean;
  writable: boolean;
  provider: string;
};
export type Agenda = {
  start: string;
  end: string;
  timezone: string;
  events: CalendarEvent[];
  tasks: CalendarTask[];
  calendars: CalendarSource[];
  warnings: string[];
  status: string;
  tasks_status: string;
  fetched_at: string;
};
export type CalendarDraft = {
  id: string;
  title: string;
  start: string;
  end: string;
  all_day: boolean;
  calendar_id: string;
  calendar_name: string;
  timezone: string;
  location: string;
  notes: string;
  reminder_minutes: number;
};
export function dayInZone(value: string | Date, timezone: string) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone: timezone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(value));
}
export function shiftDay(day: string, amount: number) {
  const d = new Date(`${day}T12:00:00Z`);
  d.setUTCDate(d.getUTCDate() + amount);
  return d.toISOString().slice(0, 10);
}
export function useCalendar(
  session: Session | null,
  online: boolean,
  accountKey: number,
) {
  const tz = session?.user.profile.timezone || "UTC";
  const [start, setStart] = useState(() => dayInZone(new Date(), tz));
  const [days, setDays] = useState(7);
  const [agenda, setAgenda] = useState<Agenda | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const request = useRef<AbortController | null>(null);
  const end = shiftDay(start, days);
  useEffect(() => {
    setStart(dayInZone(new Date(), tz));
    setAgenda(null);
    setError("");
  }, [accountKey, session?.user.id, tz]);
  const refresh = useCallback(async () => {
    request.current?.abort();
    if (!online || !session) {
      setAgenda(null);
      setLoading(false);
      return;
    }
    const controller = new AbortController();
    request.current = controller;
    setLoading(true);
    setError("");
    try {
      const next = await api<Agenda>(
        `/api/calendar/agenda?start=${start}&end=${end}`,
        { signal: controller.signal },
      );
      if (!controller.signal.aborted) setAgenda(next);
    } catch (e) {
      if (!controller.signal.aborted) {
        setError((e as Error).message || "Your calendar could not refresh.");
        setAgenda(null);
      }
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, [online, session?.user.id, start, end, accountKey]);
  useEffect(() => {
    setAgenda(null);
    void refresh();
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") void refresh();
    }, 60000);
    const focus = () => {
      void refresh();
    };
    window.addEventListener("focus", focus);
    return () => {
      clearInterval(timer);
      window.removeEventListener("focus", focus);
      request.current?.abort();
    };
  }, [refresh]);
  return {
    agenda,
    loading,
    error,
    start,
    end,
    days,
    setStart,
    setDays,
    refresh,
    timezone: tz,
    online,
  };
}
export type CalendarData = ReturnType<typeof useCalendar>;
