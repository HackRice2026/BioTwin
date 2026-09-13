"""One-hour Body Battery forecast, evaluated from exported coefficients.

The model is a ridge regression fitted in matlab/export_forecast_params.py and
stored as plain numbers, so nothing here depends on MATLAB at run time -- the
same arrangement used for the recovery constant.

It forecasts Garmin's Body Battery, a proprietary composite, and not "energy".
Its dominant input by far is the current Body Battery level (standardised
coefficient +19.97 against +4.56 for the next largest), so a stale level would
produce a confidently wrong number. Rather than extrapolate from one, the
forecast is refused and says why.
"""

import json
import math
from datetime import timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

PARAMS_PATH = Path(__file__).resolve().parents[1] / "matlab" / "params_forecast.json"

# Training rows carried a Body Battery reading at most 2 minutes old, and the
# watch reports roughly every 5 minutes. Beyond this the level is too old for a
# model that leans on it this heavily.
MAX_LEVEL_AGE = timedelta(minutes=20)
# The change feature is the level now minus the level an hour ago; a reading has
# to fall near that mark to stand in for it.
CHANGE_WINDOW = (timedelta(minutes=45), timedelta(minutes=90))


def load_params(path=PARAMS_PATH):
    with open(path) as fh:
        return json.load(fh)


def _latest(history, field, now, within=None):
    """Most recent non-null reading of one field, optionally within a window."""
    best = None
    for frame in history:
        value = getattr(frame, field, None)
        if value is None or frame.event_time > now:
            continue
        if within is not None and now - frame.event_time > within:
            continue
        if best is None or frame.event_time > best.event_time:
            best = frame
    return best


def features(history, now, timezone="UTC"):
    """Assemble the model's inputs from stored measurements.

    Returns the values, whichever inputs were unavailable, and the age of the
    Body Battery reading, so a caller can decide whether to show a number.
    """
    local = now.astimezone(ZoneInfo(timezone))
    hour = local.hour + local.minute / 60
    values = {
        # Convention taken from the training table: sin/cos of the fraction of a
        # day, not of the hour index.
        "hour_sin": math.sin(2 * math.pi * hour / 24),
        "hour_cos": math.cos(2 * math.pi * hour / 24),
    }
    missing = []

    level = _latest(history, "body_battery_pct", now, MAX_LEVEL_AGE)
    if level is None:
        return None, ["body_battery_pct"], None
    values["bb_current_measured"] = float(level.body_battery_pct)
    age = now - level.event_time

    # Change over the last hour, from the reading closest to an hour before the
    # current one. Absent an earlier reading the trend is taken as flat, which is
    # what the training data did when the column was missing.
    earlier, target = None, level.event_time - timedelta(hours=1)
    for frame in history:
        if frame.body_battery_pct is None:
            continue
        gap = abs(frame.event_time - target)
        if CHANGE_WINDOW[0] <= level.event_time - frame.event_time <= CHANGE_WINDOW[1]:
            if earlier is None or gap < abs(earlier.event_time - target):
                earlier = frame
    if earlier is None:
        values["bb_current_change_1h"] = 0.0
        missing.append("bb_current_change_1h")
    else:
        values["bb_current_change_1h"] = float(
            level.body_battery_pct - earlier.body_battery_pct)

    heart = _latest(history, "heart_rate_bpm", now, timedelta(hours=6))
    if heart is None:
        missing.append("hr_last")
    else:
        values["hr_last"] = float(heart.heart_rate_bpm)

    sleep = _latest(history, "sleep", now, timedelta(days=2))
    values["has_sleep_context"] = 1.0 if sleep is not None else 0.0
    if sleep is not None and sleep.sleep.rem_minutes is not None:
        values["rem_sleep_min"] = float(sleep.sleep.rem_minutes)
    else:
        missing.append("rem_sleep_min")

    stress = _latest(history, "stress_max", now, timedelta(days=2))
    if stress is None:
        missing.append("stress_max")
    else:
        values["stress_max"] = float(stress.stress_max)

    return values, missing, age


def predict(history, now, timezone="UTC", params=None):
    """Forecast Body Battery one hour out, or explain why it cannot.

    Inputs that are absent fall back to their training mean, which is the value
    the standardised model treats as "unremarkable" -- it contributes nothing
    rather than pulling the estimate. Which inputs were filled is reported, so
    the caller can say so instead of presenting a guess as a measurement.
    """
    params = params or load_params()
    values, missing, age = features(history, now, timezone)
    if values is None:
        return {
            "available": False,
            "reason": "No Body Battery reading in the last 20 minutes. "
                      "The forecast leans on the current level and will not "
                      "extrapolate from a stale one.",
            "missing": missing,
        }

    total = params["intercept"]
    for name, mean, std, coef in zip(
            params["features"], params["mean"], params["std"], params["coef"]):
        x = values.get(name, mean)
        total += coef * (x - mean) / (std or 1.0)
    low, high = params["clip"]

    return {
        "available": True,
        "horizon_minutes": params["horizon_minutes"],
        "current": round(values["bb_current_measured"], 1),
        "forecast": round(min(high, max(low, total)), 1),
        "validation_mae": params["validation"]["mae"],
        "measured_age_minutes": round(age.total_seconds() / 60, 1),
        "imputed_inputs": missing,
        "model": f'{params["model"]} on {len(params["features"])} inputs, '
                 f'{params["fitted_on"]["days"]} days',
    }


TRAJECTORY_PATH = Path(__file__).resolve().parents[1] / "matlab" / "params_trajectory.json"


def load_trajectory_params(path=TRAJECTORY_PATH):
    return json.loads(Path(path).read_text())


MEASURED_WINDOW = timedelta(hours=12)


def trajectory(history, now, timezone="UTC", params=None, extra=None):
    """The measured Body Battery behind, and a prediction ahead, always drawable.

    Two things get decided here.

    Which predictor per horizon. The ridge wins at an hour and loses past it: at
    three hours a linear extrapolation averaged with this person's hour-of-day
    rhythm scores 5.20 against its 6.32, and at six the rhythm alone scores 7.37
    against its 9.21. Each point carries the method that drew it and that
    method's validation error, so the band widens because the predictors
    genuinely get worse.

    What to do when the current reading is stale. The ridge still must not claim
    to forecast from now. Instead, it is replayed at the last real watch sample,
    using only measurements available at that instant. The API labels that path
    as a historical replay and returns its anchor time, so the UI cannot mistake
    it for a live forecast.
    """
    spec = extra or load_trajectory_params()

    def measured_at(reference, source):
        return [
            {"minutes_ago": round((reference - f.event_time).total_seconds() / 60, 1),
             "value": round(float(f.body_battery_pct), 1)}
            for f in sorted(source, key=lambda f: f.event_time)
            if getattr(f, "body_battery_pct", None) is not None
            and timedelta(0) <= reference - f.event_time <= MEASURED_WINDOW
        ]

    def clock_at(reference, name, minutes):
        local = reference.astimezone(ZoneInfo(timezone))
        target_hour = (local.hour + (local.minute + minutes) // 60) % 24
        return spec["horizons"][name]["climatology_by_target_hour"][target_hour]

    def model_points(source, reference, first):
        current, change = first["current"], _change_per_hour(source, reference)
        points = [{
            "horizon_minutes": first["horizon_minutes"],
            "value": first["forecast"],
            "validation_mae": first["validation_mae"],
            "method": "ridge",
            "beats_baseline": True,
        }]
        for name, horizon in _ordered(spec):
            if horizon["minutes"] <= first["horizon_minutes"]:
                continue
            minutes = horizon["minutes"]
            clock = clock_at(reference, name, minutes)
            value = clock if horizon["method"] == "time_of_day" else (
                _clip((_clip(current + change / 60 * minutes) + clock) / 2))
            points.append({
                "horizon_minutes": minutes,
                "value": round(value, 1),
                "validation_mae": horizon["validation_mae"],
                "method": horizon["method"],
                "beats_baseline": False,
            })
        return points

    first = predict(history, now, timezone, params)
    if first["available"]:
        return {
            "available": True,
            "basis": "model",
            "anchor_time": now.isoformat(),
            "current": first["current"],
            "measured_age_minutes": first["measured_age_minutes"],
            "imputed_inputs": first["imputed_inputs"],
            "measured": measured_at(now, history),
            "points": model_points(history, now, first),
            "model": first["model"],
            "note": spec["note"],
        }

    # A stale reading cannot support a forecast from now. Replay the actual
    # fitted model at the latest recorded sample and exclude all later frames,
    # which prevents future information from leaking into that historical run.
    anchor_frame = _latest(history, "body_battery_pct", now)
    if anchor_frame is None:
        return first
    anchor = anchor_frame.event_time
    replay_history = [frame for frame in history if frame.event_time <= anchor]
    replay = predict(replay_history, anchor, timezone, params)
    if not replay["available"]:
        return first
    age_minutes = round((now - anchor).total_seconds() / 60, 1)
    hours = age_minutes / 60
    return {
        "available": True,
        "basis": "replay",
        "anchor_time": anchor.isoformat(),
        "current": replay["current"],
        "measured_age_minutes": age_minutes,
        "imputed_inputs": replay["imputed_inputs"],
        "measured": measured_at(anchor, replay_history),
        "points": model_points(replay_history, anchor, replay),
        "model": replay["model"],
        "reason": (
            f"Historical MATLAB model replay anchored to your last recorded "
            f"Body Battery sample ({hours:.1f} hours old). It uses only data "
            f"available at that sync and is not a forecast from now."
        ),
        "note": spec["note"],
    }


def _ordered(spec):
    return sorted(spec["horizons"].items(), key=lambda kv: kv[1]["minutes"])


def _clip(value, low=0.0, high=100.0):
    return max(low, min(high, value))


def _change_per_hour(history, now):
    """Body Battery change per hour, from the same 45-90 minute lookback the
    ridge uses, so the two horizons cannot disagree about the recent trend."""
    level = _latest(history, "body_battery_pct", now, MAX_LEVEL_AGE)
    if level is None:
        return 0.0
    earliest, latest = CHANGE_WINDOW
    earlier = None
    for frame in sorted(history, key=lambda f: f.event_time, reverse=True):
        if getattr(frame, "body_battery_pct", None) is None:
            continue
        gap = level.event_time - frame.event_time
        if earliest <= gap <= latest:
            earlier = frame
            break
    if earlier is None:
        return 0.0
    hours = (level.event_time - earlier.event_time).total_seconds() / 3600
    return (level.body_battery_pct - earlier.body_battery_pct) / (hours or 1.0)
