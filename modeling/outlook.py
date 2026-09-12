"""Explicit engineering projection, separate from measured recovery forecasting."""

import math
from datetime import timedelta
from zoneinfo import ZoneInfo
from shared.schemas import DayOutlook, CurvePoint


def daily_outlook(state, profile, now):
    tz = ZoneInfo(profile.get("timezone", "UTC"))
    local = now.astimezone(tz)
    ready = state.readiness
    assumption = (
        "Anchored to your current computed readiness. The time-of-day shape and gradual waking-time decline "
        "are fixed engineering assumptions, not learned physiological effects. Sleep and recent recovery signals "
        "influence the starting score. This projection has not been validated as a full-day forecast."
    )
    if ready.score is None:
        return DayOutlook(
            issued_at=now,
            timezone=str(tz),
            curve=[],
            confidence=0,
            assumptions="Recent sleep, HRV or resting-heart-rate data are needed before a day outlook is available.",
        )

    def circadian(hour):
        return 4 * math.cos((hour - 10) / 24 * 2 * math.pi) - 5 * math.exp(-(((hour - 14) / 1.5) ** 2))

    initial = local.hour + local.minute / 60
    points = []
    for hour in range(min(12, 24 - local.hour)):
        stamp = local + timedelta(hours=hour)
        score = max(0, min(100, ready.score + circadian(initial + hour) - circadian(initial) - 0.6 * hour))
        points.append(CurvePoint(time=stamp, value=round(score, 1)))
    return DayOutlook(
        issued_at=now,
        timezone=str(tz),
        curve=points,
        confidence=ready.confidence * 0.4,
        assumptions=assumption,
    )
