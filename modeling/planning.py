from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import hashlib
import math
from shared.schemas import Proposal, DailyPlan


def overlaps(start, end, intervals):
    return any(start < b.end and end > b.start for b in intervals)


def make_plan(now, ready, busy, profile, status="unavailable"):
    tz = ZoneInfo(profile.get("timezone", "UTC"))
    local = now.astimezone(tz)
    bedtime = datetime.combine(local.date(), time.fromisoformat(profile.get("bedtime", "23:00")), tz)
    if bedtime.hour < 6:
        bedtime += timedelta(days=1)
    if ready.score is None:
        return DailyPlan(
            date=str(local.date()),
            timezone=str(tz),
            calendar_status=status,
            proposals=[],
            busy=busy,
            explanation="Recent sleep, RMSSD HRV, or daily resting-heart-rate measurements are needed to estimate readiness and build your daily plan.",
        )
    if status == "unavailable":
        return DailyPlan(
            date=str(local.date()),
            timezone=str(tz),
            calendar_status=status,
            proposals=[],
            busy=[],
            explanation="Schedule unavailable. Connect Google Calendar to find verified free windows.",
        )
    start = local.replace(minute=local.minute // 15 * 15, second=0, microsecond=0) + timedelta(minutes=15)
    end_day = datetime.combine(local.date(), time(22), tz)
    candidates = []
    for kind in ["nap", "workout"]:
        intensity = (
            "mobility"
            if ready.state.value in ["very_drained", "drained"]
            else "light"
            if ready.score < 65
            else "moderate"
            if ready.score < 83
            else "vigorous"
        )
        duration = 20 if kind == "nap" else int(profile.get("workout_minutes", 30))
        cursor = start
        while cursor + timedelta(minutes=duration) <= end_day:
            end = cursor + timedelta(minutes=duration)
            legal = not overlaps(cursor, end, busy)
            if kind == "nap":
                legal &= bool(profile.get("naps_enabled", True)) and end <= bedtime - timedelta(hours=6)
            else:
                legal &= end <= bedtime - timedelta(hours=3)
            if legal:
                hour = cursor.hour + cursor.minute / 60
                circadian = math.exp(-(((hour - (14 if kind == "nap" else 17)) / 2) ** 2))
                debt = min(1, (ready.sleep_debt_minutes or 0) / 240)
                terms = {
                    "time_preference": round(circadian, 3),
                    "sleep_debt": round(debt if kind == "nap" else 0, 3),
                    "free_slot": 1.0,
                }
                score = circadian * 0.6 + (debt * 0.3 if kind == "nap" else 0.3) + 0.1
                label = "Power nap" if kind == "nap" else f"{intensity.title()} movement"
                reason = f"Readiness {ready.score}; a free {duration}-minute window. "
                reason += (
                    "Ends well before your bedtime."
                    if kind == "nap"
                    else f"Intensity capped at {intensity} by the readiness model."
                )
                key = hashlib.sha256(
                    f"{local.date()}|{kind}|{cursor.isoformat()}|{duration}".encode()
                ).hexdigest()[:24]
                candidates.append(
                    Proposal(
                        id=key,
                        kind=kind,
                        title=label,
                        start=cursor,
                        end=end,
                        intensity="rest" if kind == "nap" else intensity,
                        reason=reason,
                        score=round(score, 3),
                        terms=terms,
                    )
                )
            cursor += timedelta(minutes=15)
    selected = []
    for candidate in sorted(candidates, key=lambda c: c.score, reverse=True):
        if any(p.kind == candidate.kind for p in selected) or overlaps(
            candidate.start, candidate.end, selected
        ):
            continue
        selected.append(candidate)
    return DailyPlan(
        date=str(local.date()),
        timezone=str(tz),
        calendar_status=status,
        proposals=sorted(selected, key=lambda p: p.start),
        busy=busy,
        explanation="Estimated options fitted around your availability. Benefits and timing preferences use documented engineering assumptions.",
    )
