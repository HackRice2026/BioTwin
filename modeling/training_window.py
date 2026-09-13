"""Best Training Window: when to train today, decided by rules over validated inputs.

    current state (readiness) + near-term forecast (forecast.trajectory)
    + calendar (busy intervals) + workout needs (duration, readiness-capped intensity)
    -> one recommended window, the projected day, alternatives, and stretches to avoid

Deterministic on purpose: the voice coach receives this as grounding and can only
explain it, never pick a different window. Two kinds of number leave this module and
they are kept apart everywhere they are shown:

* Projected energy is Garmin Body Battery from the per-horizon predictors that
  forecast.trajectory already selects by validation error (ridge to 1h, trend + the
  person's hour-of-day rhythm to 3h, the rhythm alone beyond). Each slot's confidence
  label follows that predictor's measured error, so the curve only reads "High"
  where a model earned it; past 3h it is rhythm plus calendar, not physiology.
* Session drain and recovery load are engineering assumptions (DRAIN_PER_MIN), not
  fitted from data, and carry DRAIN_ASSUMPTION wherever they surface.
"""

import math
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from modeling.forecast import load_params, load_trajectory_params

STEP = timedelta(minutes=5)
BUFFER = timedelta(minutes=10)
MAX_WINDOW = timedelta(minutes=90)
RISK_BLOCK = timedelta(hours=2)
RECOVERY_THRESHOLD = 50
INTENSITIES = ["mobility", "light", "moderate", "vigorous"]
DRAIN_PER_MIN = {"mobility": 0.1, "light": 0.2, "moderate": 0.35, "vigorous": 0.55}
DRAIN_ASSUMPTION = (
    "Session drain uses fixed per-minute Body Battery costs by intensity and ignores "
    "recharge afterwards. It is an engineering assumption, not a fitted model."
)
CONFIDENCE_WEIGHT = {"High": 1.0, "Moderate": 0.7, "Low": 0.4}


def _confidence(mae):
    return "High" if mae <= 3 else "Moderate" if mae <= 6 else "Low"


def _ceil_step(stamp):
    stamp = stamp.replace(second=0, microsecond=0)
    return stamp + timedelta(minutes=(-stamp.minute) % 5)


def _minutes(stamp, local):
    return max(0, int((stamp - local).total_seconds() // 60))


def _energy_model(trajectory, local, spec):
    """Returns f(minutes_ahead) -> (value, validation_mae, method), or None."""
    if not trajectory or not trajectory.get("available"):
        return None
    rhythm = spec["horizons"]["6h"]
    by_hour = rhythm["climatology_by_target_hour"]
    rhythm_mae = rhythm["alternatives"]["time_of_day"]

    def clock(minutes):
        target = local + timedelta(minutes=minutes)
        hour = target.hour + target.minute / 60
        low = int(hour)
        return by_hour[low % 24] + (by_hour[(low + 1) % 24] - by_hour[low % 24]) * (hour - low)

    if trajectory["basis"] != "model":
        return lambda minutes: (clock(minutes), rhythm_mae, "time_of_day")

    points = trajectory["points"]
    anchors = [(0, trajectory["current"], points[0]["validation_mae"], "measured")] + [
        (p["horizon_minutes"], p["value"], p["validation_mae"], p["method"]) for p in points
    ]

    def at(minutes):
        if minutes > anchors[-1][0]:
            return clock(minutes), rhythm_mae, "time_of_day"
        for (m0, v0, _, _), (m1, v1, mae, method) in zip(anchors, anchors[1:]):
            if m0 <= minutes <= m1:
                return v0 + (v1 - v0) * (minutes - m0) / (m1 - m0), mae, method
        return anchors[0][1], anchors[1][2], "measured"

    return at


def _intensity(readiness, energy):
    if readiness.score is None:
        cap = "moderate"
    elif str(readiness.state) in ("very_drained", "drained"):
        cap = "mobility"
    elif readiness.score < 65:
        cap = "light"
    elif readiness.score < 83:
        cap = "moderate"
    else:
        cap = "vigorous"
    by_energy = "light" if energy < 30 else "moderate" if energy < 55 else "vigorous"
    return INTENSITIES[min(INTENSITIES.index(cap), INTENSITIES.index(by_energy))]


def _session(key, start, duration, energy_at, local, readiness, evening_at):
    energy = energy_at(_minutes(start, local))[0]
    intensity = _intensity(readiness, energy)
    drain = DRAIN_PER_MIN[intensity] * duration
    evening = max(0.0, energy_at(_minutes(evening_at, local))[0] - drain)
    ratio = drain / max(energy, 1.0)
    load = "High" if ratio >= 0.4 or energy - drain < 20 else "Medium" if ratio >= 0.2 else "Low"
    return {
        "key": key,
        "start": start.isoformat(),
        "energy": round(energy),
        "evening_energy": round(evening),
        "recovery_load": load,
        "intensity": intensity,
    }


def model_details(spec=None, forecast=None):
    """What runs here per horizon, beside what MATLAB found. The tree models are
    MATLAB-toolbox results from matlab/results/BASELINES.md ("Stage 3"); they cannot
    run inside this server, so they are reported next to the deployed predictor
    rather than presented as the thing producing the forecast."""
    spec = spec or load_trajectory_params()
    forecast = forecast or load_params()
    return [
        {
            "horizon": "1 hour",
            "matlab_model": "Boosted Trees",
            "matlab_mae": 1.92,
            "baseline": "Trend extrapolation",
            "baseline_mae": 2.35,
            "running": "Ridge regression",
            "running_mae": round(forecast["validation"]["mae"], 2),
            "ml_wins": True,
        },
        {
            "horizon": "3 hours",
            "matlab_model": "Bagged Trees",
            "matlab_mae": 4.84,
            "baseline": "Trend + time of day",
            "baseline_mae": 5.2,
            "running": "Trend + time of day",
            "running_mae": round(spec["horizons"]["3h"]["validation_mae"], 2),
            "ml_wins": True,
        },
        {
            "horizon": "6 hours",
            "matlab_model": "Bagged Trees",
            "matlab_mae": 8.47,
            "baseline": "Time of day",
            "baseline_mae": 7.37,
            "running": "Time of day",
            "running_mae": round(spec["horizons"]["6h"]["validation_mae"], 2),
            "ml_wins": False,
        },
    ]


def _risks(intervals, energy_at, local, horizon_end):
    flagged = []
    cursor = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    while cursor + RISK_BLOCK <= horizon_end:
        end = cursor + RISK_BLOCK
        overlapping = [(s, e) for s, e, _ in intervals if s < end and e > cursor]
        busy_minutes = sum((min(e, end) - max(s, cursor)).total_seconds() / 60 for s, e in overlapping)
        before = round(energy_at(_minutes(cursor, local))[0])
        after = round(energy_at(_minutes(end, local))[0])
        if (len(overlapping) >= 2 or busy_minutes >= 60) and after < before - 2:
            count = len(overlapping)
            flagged.append(
                {
                    "start": cursor,
                    "end": end,
                    "weight": (before - after) * busy_minutes,
                    "reasons": [
                        f"Energy falling from {before} to {after}",
                        f"{count} calendar event{'s' if count != 1 else ''}",
                    ],
                }
            )
        cursor += timedelta(hours=1)
    chosen = []
    for block in sorted(flagged, key=lambda b: b["weight"], reverse=True):
        if all(block["end"] <= c["start"] or block["start"] >= c["end"] for c in chosen):
            chosen.append(block)
        if len(chosen) == 2:
            break
    return [
        {"start": b["start"].isoformat(), "end": b["end"].isoformat(), "label": "High-load window", "reasons": b["reasons"]}
        for b in sorted(chosen, key=lambda b: b["start"])
    ]


def best_training_window(state, trajectory, busy, profile, now, calendar_status, spec=None):
    spec = spec or load_trajectory_params()
    tz = ZoneInfo(profile.get("timezone", "UTC"))
    local = now.astimezone(tz)
    readiness = state.readiness
    duration = int(profile.get("workout_minutes", 30))
    bedtime = datetime.combine(local.date(), time.fromisoformat(profile.get("bedtime", "23:00")), tz)
    if bedtime.hour < 6:
        bedtime += timedelta(days=1)
    latest_end = min(bedtime - timedelta(hours=3), datetime.combine(local.date(), time(22), tz))
    # Asked overnight, "today" still means after waking: bedtime plus the sleep target, a day back.
    wake = bedtime + timedelta(minutes=int(profile.get("target_sleep", 480))) - timedelta(days=1)
    horizon_end = max(min(bedtime - timedelta(hours=1), local + timedelta(hours=18)), local + timedelta(hours=3))
    evening_at = max(bedtime - timedelta(hours=2), local + timedelta(hours=1))
    base = {
        "issued_at": now.isoformat(),
        "timezone": str(tz),
        "calendar_status": calendar_status,
        "model_details": model_details(spec),
        "assumption": DRAIN_ASSUMPTION,
    }
    energy_at = _energy_model(trajectory, local, spec)
    if energy_at is None:
        return {
            **base,
            "available": False,
            "reason": (trajectory or {}).get("reason")
            or "Waiting for a Body Battery reading from your watch to project your day.",
        }

    intervals = sorted(
        (b.start.astimezone(tz), b.end.astimezone(tz), b.title) for b in busy if b.end.astimezone(tz) > local
    )
    horizon_minutes = _minutes(horizon_end, local)
    curve = []
    for minutes in range(0, horizon_minutes + 1, 30):
        value, mae, method = energy_at(minutes)
        curve.append(
            {
                "time": (local + timedelta(minutes=minutes)).isoformat(),
                "minutes": minutes,
                "value": round(value, 1),
                "confidence": _confidence(mae),
                "method": method,
            }
        )
    risks = _risks(intervals, energy_at, local, horizon_end)
    risk_spans = [(datetime.fromisoformat(r["start"]), datetime.fromisoformat(r["end"])) for r in risks]
    now_energy = round(energy_at(0)[0])

    recovery = None
    if now_energy < RECOVERY_THRESHOLD:
        for minutes in range(5, horizon_minutes + 1, 5):
            if energy_at(minutes)[0] >= RECOVERY_THRESHOLD:
                recovery = {
                    "threshold": RECOVERY_THRESHOLD,
                    "minutes": minutes,
                    "at": (local + timedelta(minutes=minutes)).isoformat(),
                    "confidence": _confidence(energy_at(minutes)[1]),
                }
                break
    tau = state.baseline_summary.recovery_tau_s

    shared = {
        **base,
        "now": {"time": local.isoformat(), "energy": now_energy},
        "curve": curve,
        "busy": [{"start": s.isoformat(), "end": e.isoformat(), "title": t} for s, e, t in intervals if s < horizon_end],
        "risks": risks,
        "recovery": recovery,
        "heart_rate_recovery_tau_s": round(tau) if tau else None,
        "readiness": readiness.score,
    }

    def free(start, end):
        return not any(start < e + BUFFER and end > s - BUFFER for s, e, _ in intervals)

    session = timedelta(minutes=duration)
    candidates = []
    cursor = _ceil_step(max(local + BUFFER, wake))
    while cursor + session <= latest_end:
        end = cursor + session
        if free(cursor, end):
            energy, mae, _ = energy_at(_minutes(cursor, local))
            confidence = _confidence(mae)
            gap_end = min([s - BUFFER for s, _, _ in intervals if s - BUFFER >= end] + [latest_end])
            window_end = max(end, min(gap_end, cursor + MAX_WINDOW))
            hour = cursor.hour + cursor.minute / 60
            in_risk = any(cursor < r_end and end > r_start for r_start, r_end in risk_spans)
            score = (
                0.6 * energy / 100
                + 0.15 * math.exp(-(((hour - 17) / 2.5) ** 2))
                + 0.15 * CONFIDENCE_WEIGHT[confidence]
                + 0.1 * min(1.0, (window_end - cursor) / (session + timedelta(minutes=30)))
                - (0.25 if in_risk else 0)
            )
            candidates.append((score, -cursor.timestamp(), cursor, window_end, energy, confidence))
        cursor += STEP

    if not candidates:
        return {
            **shared,
            "available": False,
            "reason": (
                f"No free {duration}-minute window left today: a session has to end by "
                f"{latest_end.strftime('%H:%M')} to stay three hours clear of your "
                f"{bedtime.strftime('%H:%M')} bedtime."
            ),
            "scenarios": [],
        }

    _, _, start, window_end, energy, confidence = max(candidates)
    if readiness.confidence < 0.4 and confidence != "Low":
        confidence = "Moderate" if confidence == "High" else "Low"
    intensity = _intensity(readiness, energy)
    window_minutes = int((window_end - start).total_seconds() // 60)
    clock = start.strftime("%I:%M %p").lstrip("0")
    reasons = []
    if round(energy) >= now_energy + 3:
        reasons.append(f"Energy projected to rise from {now_energy} to {round(energy)} by {clock}")
    elif round(energy) <= now_energy - 3:
        reasons.append(f"Energy projected at {round(energy)} by {clock}, the strongest point in your free time")
    else:
        reasons.append(f"Energy holds near {round(energy)} through {clock}")
    earlier = [(s, e, t) for s, e, t in intervals if e <= start]
    if calendar_status == "unavailable":
        reasons.append("Calendar not connected, so free time is not checked")
    elif earlier:
        reasons.append(f"{window_minutes} free minutes after {earlier[-1][2]}")
    else:
        reasons.append(f"{window_minutes} free minutes with nothing booked")
    if readiness.score is None:
        reasons.append("Readiness is not available yet, so effort is capped at moderate")
    else:
        reasons.append(f"Readiness {round(readiness.score)} supports a {intensity} effort")

    best = _session("best", start, duration, energy_at, local, readiness, evening_at)
    scenarios = []
    now_start = _ceil_step(local)
    if (
        now_start >= wake
        and free(now_start, now_start + session)
        and now_start + session <= latest_end
        and start - now_start > timedelta(minutes=20)
    ):
        scenarios.append(_session("now", now_start, duration, energy_at, local, readiness, evening_at))
    scenarios.append(best)
    scenarios.append(
        {
            "key": "rest",
            "start": None,
            "energy": None,
            "evening_energy": round(energy_at(_minutes(evening_at, local))[0]),
            "recovery_load": "Low",
            "intensity": "rest",
        }
    )
    recommended = "rest" if best["energy"] < 25 else "best"
    for option in scenarios:
        option["recommended"] = option["key"] == recommended

    return {
        **shared,
        "available": True,
        "window": {
            "start": start.isoformat(),
            "end": window_end.isoformat(),
            "minutes": window_minutes,
            "energy": round(energy),
            "confidence": confidence,
            "workout": {"title": f"{intensity.title()} session", "intensity": intensity, "minutes": duration},
            "reasons": reasons,
        },
        "evening_at": evening_at.isoformat(),
        "scenarios": scenarios,
    }
