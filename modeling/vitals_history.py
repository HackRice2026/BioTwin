"""Turns raw per-account TwinFrame history into plain-language "yesterday" and
"past 7 days" vitals facts, so narrate() has something grounded to answer with when
asked a simple recap question -- otherwise those facts don't exist anywhere and the
model correctly (but unhelpfully) has to say it doesn't know.

Aggregation matches how each field is actually reported, not a blind average:
counters like steps or active calories are cumulative through the day, so a day's
value is its max, not a mean of every intraday sample; continuous signals like
heart rate are averaged across the day's samples; resting HR and sleep are each
reported once (or once effectively) per day, so the day's last reading is used.
"""

from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo

CUMULATIVE = ("steps", "active_kcal", "total_calories")
AVERAGED = ("heart_rate_bpm", "respiration_brpm", "spo2_pct", "hrv_rmssd_ms")
LAST_OF_DAY = ("resting_hr_bpm",)

LABELS = {
    "heart_rate_bpm": ("average heart rate", "beats per minute"),
    "resting_hr_bpm": ("resting heart rate", "beats per minute"),
    "hrv_rmssd_ms": ("HRV RMSSD", "milliseconds"),
    "respiration_brpm": ("respiration", "breaths per minute"),
    "spo2_pct": ("oxygen saturation", "percent"),
    "steps": ("steps", "steps"),
    "active_kcal": ("active calories burned", "kilocalories"),
    "sleep_minutes": ("sleep", "minutes"),
}
# Fixed order so the sentence reads naturally and is stable across calls.
ORDER = ("resting_hr_bpm", "heart_rate_bpm", "hrv_rmssd_ms", "respiration_brpm", "spo2_pct", "sleep_minutes", "steps", "active_kcal")


def _daily_aggregates(history, tz):
    by_day = defaultdict(list)
    for frame in history:
        by_day[frame.event_time.astimezone(tz).date()].append(frame)
    days = {}
    for day, frames in by_day.items():
        agg = {}
        for metric in CUMULATIVE:
            values = [getattr(f, metric) for f in frames if getattr(f, metric) is not None]
            if values:
                agg[metric] = max(values)
        for metric in AVERAGED:
            values = [getattr(f, metric) for f in frames if getattr(f, metric) is not None]
            if values:
                agg[metric] = sum(values) / len(values)
        for metric in LAST_OF_DAY:
            dated = [(f.event_time, getattr(f, metric)) for f in frames if getattr(f, metric) is not None]
            if dated:
                agg[metric] = max(dated, key=lambda x: x[0])[1]
        sleep_minutes = [f.sleep.total_minutes for f in frames if f.sleep is not None]
        if sleep_minutes:
            agg["sleep_minutes"] = sleep_minutes[-1]
        days[day] = agg
    return days


def _sentence(lead, aggregate, day_count=None):
    parts = []
    for metric in ORDER:
        if metric not in aggregate:
            continue
        label, unit = LABELS[metric]
        value = aggregate[metric]
        suffix = f" (averaged across {day_count} of the last 7 days)" if day_count else ""
        parts.append(f"{label} was {value:g} {unit}{suffix}")
    if not parts:
        return None
    return f"{lead}, your " + ", ".join(parts) + "."


def vitals_summary_facts(history, tz_name, now):
    """Returns up to two facts: yesterday's recap and a past-7-days recap, each
    built only from days that actually have data -- a day with nothing recorded
    is silently skipped rather than reported as zero."""
    if not history:
        return ()
    tz = ZoneInfo(tz_name)
    days = _daily_aggregates(history, tz)
    today = now.astimezone(tz).date()
    facts = []
    yesterday = today - timedelta(days=1)
    if yesterday in days:
        sentence = _sentence(f"Yesterday ({yesterday.isoformat()})", days[yesterday])
        if sentence:
            facts.append(sentence)
    window = [days[d] for d in days if 1 <= (today - d).days <= 7]
    if window:
        merged = {}
        for metric in LABELS:
            values = [d[metric] for d in window if metric in d]
            if values:
                merged[metric] = sum(values) / len(values)
        sentence = _sentence("Over the past 7 days", merged, day_count=len(window))
        if sentence:
            facts.append(sentence)
    return tuple(facts)
