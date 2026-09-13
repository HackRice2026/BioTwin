#!/usr/bin/env python3
"""Build a leakage-aware 15-minute Garmin training table for MATLAB.

Run from the repo root:
    python scripts/build_garmin_master.py

Expected inputs (default: raw_json/):
    activities.json
    body_battery_daily.json
    heart_rates.json
    respiration.json
    sleep.json
    stats_and_body.json
    stress.json

Output (default):
    processed_data/garmin_15min_master.csv

The script intentionally does NOT use all_day_stress.json, daily_steps.json,
weekly_steps.json, weekly_stress.json, or body_battery_events.json because they
are duplicate/redundant/empty for this training table.

Important modeling rule:
- Body Battery values between real Garmin anchor points are interpolated only
  for historical TARGET construction. Future anchor information is never used
  as an input feature.
- Daily summary features are made available only after that day has ended.
- Sleep features are made available only after the sleep episode has ended.
This prevents future-data leakage during model training.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

FREQ = "15min"
BB_MAX_INTERPOLATION_GAP_HOURS = 24.0


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def ms_to_utc(value):
    if value is None:
        return pd.NaT
    try:
        return pd.to_datetime(int(value), unit="ms", utc=True)
    except (TypeError, ValueError, OverflowError):
        return pd.NaT


def parse_utc_string(value):
    if not value:
        return pd.NaT
    return pd.to_datetime(value, utc=True, errors="coerce")


def safe_num(value):
    if value is None or isinstance(value, bool):
        return np.nan
    try:
        return float(value)
    except (TypeError, ValueError):
        return np.nan


def series_from_garmin_days(days, array_key: str, value_min: float, value_max: float):
    """Extract [timestamp_ms, value] arrays into a clean UTC time series."""
    rows = []
    for item in days:
        payload = item.get("data") or {}
        for pair in payload.get(array_key) or []:
            if not isinstance(pair, list) or len(pair) < 2:
                continue
            ts = ms_to_utc(pair[0])
            value = safe_num(pair[1])
            if pd.isna(ts) or pd.isna(value):
                continue
            if value_min <= value <= value_max:
                rows.append((ts, value))
    if not rows:
        return pd.DataFrame(columns=["timestamp_utc", "value"])
    df = pd.DataFrame(rows, columns=["timestamp_utc", "value"])
    # Garmin can occasionally return the same timestamp twice.
    return (
        df.groupby("timestamp_utc", as_index=False)["value"]
        .mean()
        .sort_values("timestamp_utc")
    )


def _window_slope(series: pd.Series):
    series = series.dropna()
    if len(series) < 2:
        return np.nan
    x = (series.index.view("int64") - series.index[0].value) / 60_000_000_000.0
    y = series.to_numpy(dtype=float)
    if np.allclose(x, x[0]):
        return np.nan
    return float(np.polyfit(x, y, 1)[0])  # units per minute


def resample_sensor(df: pd.DataFrame, prefix: str):
    """15-minute sensor statistics, including slope and sample count."""
    if df.empty:
        return pd.DataFrame()
    s = df.set_index("timestamp_utc")["value"].sort_index()
    rs = s.resample(FREQ, label="left", closed="left")
    out = pd.DataFrame({
        f"{prefix}_mean": rs.mean(),
        f"{prefix}_min": rs.min(),
        f"{prefix}_max": rs.max(),
        f"{prefix}_std": rs.std(ddof=0),
        f"{prefix}_last": rs.last(),
        f"{prefix}_count": rs.count(),
        f"{prefix}_slope_per_min": rs.apply(_window_slope),
    })
    return out


def build_day_boundaries(*day_sets):
    """Create UTC day boundaries + local offset from any Garmin day wrapper."""
    rows = []
    for days in day_sets:
        for item in days:
            d = item.get("data") or {}
            gmt = parse_utc_string(d.get("startTimestampGMT") or d.get("wellnessStartTimeGmt"))
            local_raw = d.get("startTimestampLocal") or d.get("wellnessStartTimeLocal")
            if pd.isna(gmt) or not local_raw:
                continue
            # Local string intentionally parsed as naive so we can recover offset.
            local_naive = pd.to_datetime(local_raw, errors="coerce")
            if pd.isna(local_naive):
                continue
            gmt_naive = gmt.tz_convert("UTC").tz_localize(None)
            offset_hours = (local_naive - gmt_naive).total_seconds() / 3600.0
            end_gmt = parse_utc_string(d.get("endTimestampGMT") or d.get("wellnessEndTimeGmt"))
            rows.append({
                "day_start_utc": gmt,
                "day_end_utc": end_gmt,
                "local_offset_hours": offset_hours,
                "garmin_calendar_date": item.get("date") or d.get("calendarDate"),
            })
    if not rows:
        return pd.DataFrame()
    b = pd.DataFrame(rows).drop_duplicates("day_start_utc").sort_values("day_start_utc")
    return b


def attach_local_time(master: pd.DataFrame, boundaries: pd.DataFrame):
    out = master.copy()
    if boundaries.empty:
        out["local_offset_hours"] = 0.0
        out["local_timestamp"] = out["timestamp_utc"].dt.tz_convert(None)
    else:
        temp = pd.merge_asof(
            out.sort_values("timestamp_utc"),
            boundaries.sort_values("day_start_utc"),
            left_on="timestamp_utc",
            right_on="day_start_utc",
            direction="backward",
        )
        valid = temp["day_end_utc"].isna() | (temp["timestamp_utc"] < temp["day_end_utc"])
        temp.loc[~valid, ["local_offset_hours", "garmin_calendar_date"]] = np.nan
        temp["local_offset_hours"] = temp["local_offset_hours"].ffill().bfill().fillna(0.0)
        # Store local clock time without timezone metadata; offset is retained separately.
        temp["local_timestamp"] = (
            temp["timestamp_utc"].dt.tz_convert(None)
            + pd.to_timedelta(temp["local_offset_hours"], unit="h")
        )
        out = temp

    hour = out["local_timestamp"].dt.hour + out["local_timestamp"].dt.minute / 60.0
    dow = out["local_timestamp"].dt.dayofweek.astype(float)
    out["hour_sin"] = np.sin(2 * np.pi * hour / 24.0)
    out["hour_cos"] = np.cos(2 * np.pi * hour / 24.0)
    out["dow_sin"] = np.sin(2 * np.pi * dow / 7.0)
    out["dow_cos"] = np.cos(2 * np.pi * dow / 7.0)
    return out


def build_body_battery_anchors(bb_days):
    rows = []
    for item in bb_days:
        for pair in item.get("bodyBatteryValuesArray") or []:
            if not isinstance(pair, list) or len(pair) < 2 or pair[1] is None:
                continue
            ts = ms_to_utc(pair[0])
            value = safe_num(pair[1])
            if pd.isna(ts) or pd.isna(value) or not (0 <= value <= 100):
                continue
            rows.append((ts, value))
    if not rows:
        return pd.DataFrame(columns=["timestamp_utc", "body_battery_anchor"])
    return (
        pd.DataFrame(rows, columns=["timestamp_utc", "body_battery_anchor"])
        .groupby("timestamp_utc", as_index=False)["body_battery_anchor"]
        .mean()
        .sort_values("timestamp_utc")
    )


def add_body_battery_labels(master: pd.DataFrame, anchors: pd.DataFrame):
    """Interpolate Body Battery ONLY as a historical target, never as a future input."""
    out = master.copy().sort_values("timestamp_utc")
    out["body_battery"] = np.nan  # historical target label
    out["bb_label_weight"] = 0.0
    out["bb_anchor_nearby"] = 0
    out["bb_gap_hours"] = np.nan
    # Causal feature: last real Garmin Body Battery anchor known at that moment.
    # Unlike the interpolated target, this never looks into the future.
    out["bb_current_last_known"] = np.nan
    out["hours_since_bb_anchor"] = np.nan

    if anchors.empty:
        return out

    a = anchors.sort_values("timestamp_utc").reset_index(drop=True)
    at = a["timestamp_utc"].astype("int64").to_numpy()
    av = a["body_battery_anchor"].to_numpy(dtype=float)
    mt = out["timestamp_utc"].astype("int64").to_numpy()

    right_idx = np.searchsorted(at, mt, side="left")
    left_idx = right_idx - 1

    values = np.full(len(out), np.nan)
    weights = np.zeros(len(out), dtype=float)
    nearby = np.zeros(len(out), dtype=int)
    gaps = np.full(len(out), np.nan)

    seven_half_min_ns = int(7.5 * 60 * 1e9)

    for i, t in enumerate(mt):
        candidates = []
        if 0 <= left_idx[i] < len(at):
            candidates.append(left_idx[i])
        if 0 <= right_idx[i] < len(at):
            candidates.append(right_idx[i])

        # A real Garmin anchor within +/- 7.5 minutes represents this 15-min bin.
        if candidates:
            nearest = min(candidates, key=lambda j: abs(at[j] - t))
            if abs(at[nearest] - t) <= seven_half_min_ns:
                values[i] = av[nearest]
                weights[i] = 1.0
                nearby[i] = 1
                gaps[i] = 0.0
                continue

        li, ri = left_idx[i], right_idx[i]
        if li < 0 or ri >= len(at) or li == ri:
            continue
        gap_hours = (at[ri] - at[li]) / 3_600_000_000_000.0
        gaps[i] = gap_hours
        if gap_hours <= 0 or gap_hours > BB_MAX_INTERPOLATION_GAP_HOURS:
            continue

        frac = (t - at[li]) / (at[ri] - at[li])
        if not 0 <= frac <= 1:
            continue
        values[i] = av[li] + frac * (av[ri] - av[li])

        # Longer gaps get less influence during training.
        if gap_hours <= 3:
            weights[i] = 0.80
        elif gap_hours <= 6:
            weights[i] = 0.65
        elif gap_hours <= 12:
            weights[i] = 0.50
        else:
            weights[i] = 0.35

    out["body_battery"] = np.clip(values, 0, 100)
    out["bb_label_weight"] = weights
    out["bb_anchor_nearby"] = nearby
    out["bb_gap_hours"] = gaps

    # Build causal current-BB feature using only anchors at or before each row.
    past_idx = np.searchsorted(at, mt, side="right") - 1
    current = np.full(len(out), np.nan)
    age_hours = np.full(len(out), np.nan)
    for i, j in enumerate(past_idx):
        if j < 0:
            continue
        age = (mt[i] - at[j]) / 3_600_000_000_000.0
        # Do not carry an old watch value forever.
        if 0 <= age <= 12:
            current[i] = av[j]
            age_hours[i] = age
    out["bb_current_last_known"] = current
    out["hours_since_bb_anchor"] = age_hours
    return out


def build_sleep_records(sleep_days):
    rows = []
    for item in sleep_days:
        payload = item.get("data") or {}
        dto = payload.get("dailySleepDTO") or {}
        end = ms_to_utc(dto.get("sleepEndTimestampGMT"))
        start = ms_to_utc(dto.get("sleepStartTimestampGMT"))
        if pd.isna(end) or pd.isna(start):
            continue
        scores = dto.get("sleepScores") or {}
        overall = scores.get("overall") or {}
        rows.append({
            "sleep_available_at": end,
            "sleep_start_utc": start,
            "sleep_end_utc": end,
            "sleep_duration_min": safe_num(dto.get("sleepTimeSeconds")) / 60.0,
            "nap_duration_min": safe_num(dto.get("napTimeSeconds")) / 60.0,
            "deep_sleep_min": safe_num(dto.get("deepSleepSeconds")) / 60.0,
            "light_sleep_min": safe_num(dto.get("lightSleepSeconds")) / 60.0,
            "rem_sleep_min": safe_num(dto.get("remSleepSeconds")) / 60.0,
            "awake_sleep_min": safe_num(dto.get("awakeSleepSeconds")) / 60.0,
            "sleep_score": safe_num(overall.get("value")),
            "sleep_avg_stress": safe_num(dto.get("avgSleepStress")),
            "sleep_avg_respiration": safe_num(dto.get("averageRespirationValue")),
            "sleep_low_respiration": safe_num(dto.get("lowestRespirationValue")),
            "sleep_high_respiration": safe_num(dto.get("highestRespirationValue")),
            "sleep_body_battery_change": safe_num(payload.get("bodyBatteryChange")),
            "sleep_resting_hr": safe_num(payload.get("restingHeartRate")),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("sleep_available_at").drop_duplicates("sleep_available_at")


def attach_completed_sleep(master: pd.DataFrame, sleep: pd.DataFrame):
    if sleep.empty:
        return master
    out = pd.merge_asof(
        master.sort_values("timestamp_utc"),
        sleep.sort_values("sleep_available_at"),
        left_on="timestamp_utc",
        right_on="sleep_available_at",
        direction="backward",
    )
    out["hours_since_sleep_end"] = (
        (out["timestamp_utc"] - out["sleep_end_utc"]).dt.total_seconds() / 3600.0
    )
    # Do not carry a stale sleep episode forever across large missing-data gaps.
    stale = out["hours_since_sleep_end"] > 48
    sleep_cols = [c for c in sleep.columns if c != "sleep_available_at"] + ["sleep_available_at", "hours_since_sleep_end"]
    out.loc[stale, [c for c in sleep_cols if c in out.columns]] = np.nan
    return out


def build_daily_summary_records(stats_days):
    rows = []
    for item in stats_days:
        d = item.get("data") or {}
        available = parse_utc_string(d.get("wellnessEndTimeGmt") or d.get("endTimestampGMT"))
        if pd.isna(available):
            continue
        rows.append({
            "prevday_available_at": available,
            "prevday_steps": safe_num(d.get("totalSteps")),
            "prevday_distance_m": safe_num(d.get("totalDistanceMeters")),
            "prevday_total_kcal": safe_num(d.get("totalKilocalories")),
            "prevday_active_kcal": safe_num(d.get("activeKilocalories")),
            "prevday_active_min": safe_num(d.get("activeSeconds")) / 60.0,
            "prevday_highly_active_min": safe_num(d.get("highlyActiveSeconds")) / 60.0,
            "prevday_sedentary_min": safe_num(d.get("sedentarySeconds")) / 60.0,
            "prevday_moderate_intensity_min": safe_num(d.get("moderateIntensityMinutes")),
            "prevday_vigorous_intensity_min": safe_num(d.get("vigorousIntensityMinutes")),
            "prevday_floors_ascended": safe_num(d.get("floorsAscended")),
            "prevday_resting_hr": safe_num(d.get("restingHeartRate")),
            "prevday_7d_resting_hr": safe_num(d.get("lastSevenDaysAvgRestingHeartRate")),
            "prevday_avg_stress": safe_num(d.get("averageStressLevel")),
            "prevday_high_stress_pct": safe_num(d.get("highStressPercentage")),
            "prevday_medium_stress_pct": safe_num(d.get("mediumStressPercentage")),
            "prevday_low_stress_pct": safe_num(d.get("lowStressPercentage")),
            "prevday_bb_charged": safe_num(d.get("bodyBatteryChargedValue")),
            "prevday_bb_drained": safe_num(d.get("bodyBatteryDrainedValue")),
            "prevday_bb_high": safe_num(d.get("bodyBatteryHighestValue")),
            "prevday_bb_low": safe_num(d.get("bodyBatteryLowestValue")),
            "prevday_bb_last": safe_num(d.get("bodyBatteryMostRecentValue")),
            "prevday_avg_spo2": safe_num(d.get("averageSpo2")),
            "prevday_low_spo2": safe_num(d.get("lowestSpo2")),
            "prevday_waking_respiration": safe_num(d.get("avgWakingRespirationValue")),
            "prevday_weight_g": safe_num(d.get("weight")),
        })
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows).sort_values("prevday_available_at").drop_duplicates("prevday_available_at")


def attach_completed_daily_summary(master: pd.DataFrame, daily: pd.DataFrame):
    if daily.empty:
        return master
    out = pd.merge_asof(
        master.sort_values("timestamp_utc"),
        daily.sort_values("prevday_available_at"),
        left_on="timestamp_utc",
        right_on="prevday_available_at",
        direction="backward",
    )
    out["hours_since_prevday_summary"] = (
        (out["timestamp_utc"] - out["prevday_available_at"]).dt.total_seconds() / 3600.0
    )
    stale = out["hours_since_prevday_summary"] > 48
    cols = [c for c in out.columns if c.startswith("prevday_")] + ["hours_since_prevday_summary"]
    out.loc[stale, cols] = np.nan
    return out


def build_activity_features(master: pd.DataFrame, activities):
    out = master.copy()
    out["workout_active"] = 0
    out["workout_type"] = "none"

    completed = []
    for a in activities:
        start = parse_utc_string(a.get("startTimeGMT"))
        end = parse_utc_string(a.get("endTimeGMT"))
        duration_sec = safe_num(a.get("duration"))
        if pd.isna(start):
            continue
        if pd.isna(end):
            if pd.isna(duration_sec) or duration_sec <= 0:
                continue
            end = start + pd.to_timedelta(duration_sec, unit="s")
        if end <= start:
            continue
        kind = ((a.get("activityType") or {}).get("typeKey") or "other")

        mask = (out["timestamp_utc"] < end) & ((out["timestamp_utc"] + pd.Timedelta(FREQ)) > start)
        out.loc[mask, "workout_active"] = 1
        # There are very few overlapping activities; latest label is sufficient.
        out.loc[mask, "workout_type"] = kind

        completed.append({
            "last_workout_end": end,
            "last_workout_type": kind,
            "last_workout_duration_min": duration_sec / 60.0 if not pd.isna(duration_sec) else (end-start).total_seconds()/60.0,
            "last_workout_calories": safe_num(a.get("calories")),
            "last_workout_steps": safe_num(a.get("steps")),
            "last_workout_avg_hr": safe_num(a.get("averageHR")),
            "last_workout_max_hr": safe_num(a.get("maxHR")),
            "last_workout_distance_m": safe_num(a.get("distance")),
            "last_workout_bb_change": safe_num(a.get("differenceBodyBattery")),
            "last_workout_moderate_min": safe_num(a.get("moderateIntensityMinutes")),
            "last_workout_vigorous_min": safe_num(a.get("vigorousIntensityMinutes")),
        })

    if completed:
        c = pd.DataFrame(completed).sort_values("last_workout_end").drop_duplicates("last_workout_end")
        out = pd.merge_asof(
            out.sort_values("timestamp_utc"),
            c,
            left_on="timestamp_utc",
            right_on="last_workout_end",
            direction="backward",
        )
        out["minutes_since_last_workout"] = (
            (out["timestamp_utc"] - out["last_workout_end"]).dt.total_seconds() / 60.0
        )
        stale = out["minutes_since_last_workout"] > (7 * 24 * 60)
        cols = [c for c in out.columns if c.startswith("last_workout_")] + ["minutes_since_last_workout"]
        out.loc[stale, cols] = np.nan
    return out


def add_rolling_features(df: pd.DataFrame):
    out = df.sort_values("timestamp_utc").copy()
    for col in ["hr_mean", "stress_mean", "resp_mean"]:
        if col in out.columns:
            out[f"{col}_1h"] = out[col].rolling(4, min_periods=1).mean()
            out[f"{col}_3h"] = out[col].rolling(12, min_periods=3).mean()

    if "bb_current_last_known" in out.columns:
        # Causal Body Battery trend features based only on values already observed.
        out["bb_current_change_1h"] = out["bb_current_last_known"].diff(4)
        out["bb_current_change_3h"] = out["bb_current_last_known"].diff(12)

    if "body_battery" in out.columns:
        # Future targets. These are LABELS only; never include them as predictors.
        for name, steps in [("30m", 2), ("1h", 4), ("3h", 12), ("6h", 24)]:
            out[f"target_bb_{name}"] = out["body_battery"].shift(-steps)
            out[f"target_bb_{name}_weight"] = out["bb_label_weight"].shift(-steps)
    return out


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-dir", default="raw_json", help="Folder containing Garmin JSON exports")
    parser.add_argument("--output", default="processed_data/garmin_15min_master.csv")
    args = parser.parse_args()

    raw = Path(args.raw_dir)
    output = Path(args.output)
    required = [
        "activities.json",
        "body_battery_daily.json",
        "heart_rates.json",
        "respiration.json",
        "sleep.json",
        "stats_and_body.json",
        "stress.json",
    ]
    missing = [name for name in required if not (raw / name).exists()]
    if missing:
        raise SystemExit(f"Missing required files in {raw}: {', '.join(missing)}")

    print("Loading Garmin JSON files...")
    activities = load_json(raw / "activities.json")
    bb_days = load_json(raw / "body_battery_daily.json")
    hr_days = load_json(raw / "heart_rates.json")
    resp_days = load_json(raw / "respiration.json")
    sleep_days = load_json(raw / "sleep.json")
    stats_days = load_json(raw / "stats_and_body.json")
    stress_days = load_json(raw / "stress.json")

    hr = series_from_garmin_days(hr_days, "heartRateValues", 25, 250)
    stress = series_from_garmin_days(stress_days, "stressValuesArray", 0, 100)
    resp = series_from_garmin_days(resp_days, "respirationValuesArray", 4, 60)

    nonempty = [x for x in [hr, stress, resp] if not x.empty]
    if not nonempty:
        raise SystemExit("No dense intraday HR/stress/respiration samples found.")

    start = min(x["timestamp_utc"].min() for x in nonempty).floor(FREQ)
    end = max(x["timestamp_utc"].max() for x in nonempty).ceil(FREQ)
    grid = pd.date_range(start=start, end=end, freq=FREQ, tz="UTC")
    master = pd.DataFrame({"timestamp_utc": grid})

    print(f"Creating {FREQ} sensor windows from {start} to {end}...")
    for sensor, prefix in [(hr, "hr"), (stress, "stress"), (resp, "resp")]:
        r = resample_sensor(sensor, prefix)
        if not r.empty:
            master = master.merge(r, left_on="timestamp_utc", right_index=True, how="left")

    boundaries = build_day_boundaries(hr_days, stress_days, stats_days)
    master = attach_local_time(master, boundaries)

    bb_anchors = build_body_battery_anchors(bb_days)
    master = add_body_battery_labels(master, bb_anchors)

    sleep = build_sleep_records(sleep_days)
    master = attach_completed_sleep(master, sleep)

    daily = build_daily_summary_records(stats_days)
    master = attach_completed_daily_summary(master, daily)

    master = build_activity_features(master, activities)
    master = add_rolling_features(master)

    # Convenient model-quality and availability fields.
    master["sensor_window_complete"] = (
        (master.get("hr_count", 0).fillna(0) >= 3)
        & (master.get("stress_count", 0).fillna(0) >= 2)
        & (master.get("resp_count", 0).fillna(0) >= 3)
    ).astype(int)

    # Keep all rows for auditing; MATLAB can filter to rows with target + predictors.
    # Remove helper columns that are not useful as numeric predictors.
    drop_helpers = ["day_start_utc", "day_end_utc"]
    master = master.drop(columns=[c for c in drop_helpers if c in master.columns])

    # ISO strings are easier for MATLAB to import consistently than mixed timezone objects.
    master["timestamp_utc"] = master["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if "local_timestamp" in master.columns:
        master["local_timestamp"] = master["local_timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    for col in [
        "sleep_available_at", "sleep_start_utc", "sleep_end_utc",
        "prevday_available_at", "last_workout_end",
    ]:
        if col in master.columns:
            master[col] = pd.to_datetime(master[col], utc=True, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%SZ")

    output.parent.mkdir(parents=True, exist_ok=True)
    master.to_csv(output, index=False)

    usable = master["body_battery"].notna().sum()
    anchors = int(master["bb_anchor_nearby"].fillna(0).sum())
    complete = int(master["sensor_window_complete"].sum())
    print("\nDone.")
    print(f"Rows: {len(master):,}")
    print(f"Columns: {len(master.columns):,}")
    print(f"Rows with Body Battery target: {usable:,}")
    print(f"15-min bins near a real Garmin BB anchor: {anchors:,}")
    print(f"Complete HR + stress + respiration windows: {complete:,}")
    print(f"Saved: {output.resolve()}")
    print("\nFor MATLAB training, do NOT use body_battery, bb_label_weight, bb_anchor_nearby,")
    print("bb_gap_hours, or target_bb_* as predictors. They are target/audit columns.")
    print("Use bb_current_last_known as the causal current Body Battery feature.")
    print("Use target_bb_*_weight as the observation weight for each forecast horizon.")


if __name__ == "__main__":
    main()
