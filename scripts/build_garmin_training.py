#!/usr/bin/env python3
"""Build leakage-safe MATLAB training tables from BioTwin's 5-minute Garmin master CSV.

Why this script exists
----------------------
The master CSV is an audit/alignment table. It intentionally contains missing values,
metadata, helper columns, and historical Body Battery labels. This script produces a
cleaner modeling table while preserving scientific validity.

Important design choices
------------------------
1. Body Battery labels are rebuilt from the dense `bodyBatteryValuesArray` embedded in
   `stress.json`, using only Garmin rows whose status is `MEASURED`.
2. Future Body Battery targets are matched to real measured readings near the requested
   horizon. They are NOT linearly interpolated across long gaps.
3. Current Body Battery is causal: only the latest measured value at or before the row
   timestamp can be used as a predictor.
4. No backward filling is used for predictors. Short sensor gaps may be forward-filled
   only in the optional imputed output.
5. Train/validation/test are split chronologically by calendar date. Preprocessing
   statistics (median/mode imputation) are learned from TRAIN only.
6. Statistical outliers are not blindly deleted. Only clearly impossible/domain-invalid
   values are set to NaN; real physiological extremes are preserved.
7. Missingness/coverage indicators are retained because missing wearable data can itself
   be informative (watch removal, charging, sync gaps, etc.).

Outputs
-------
- garmin_5min_training.csv
    Primary cleaned table. Missing predictor values are preserved. Best for tree-based
    MATLAB models that can tolerate missing predictors (or for custom preprocessing).
- garmin_5min_training_imputed.csv
    Convenience table for models that require complete numeric predictors. Uses only
    causal short forward-fill plus TRAIN-only median/mode imputation.
- garmin_training_cleaning_report.json
    Auditable counts, split dates, label counts, invalid-value counts, and dropped cols.
- garmin_feature_manifest.csv
    Predictor/target roles and feature groups for presentation and MATLAB scripting.

Research/practice references used in the design
------------------------------------------------
- scikit-learn Common Pitfalls (avoid preprocessing leakage):
  https://scikit-learn.org/stable/common_pitfalls.html
- scikit-learn TimeSeriesSplit (time-ordered evaluation; do not shuffle time series):
  https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html
- pandas interpolate/fill semantics (limit short gaps; avoid uncontrolled extrapolation):
  https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.interpolate.html
- MathWorks regression trees and missing predictors / surrogate splits:
  https://www.mathworks.com/help/stats/fitrtree.html
  https://www.mathworks.com/help/stats/surrogate-splits-for-missing-data.html
- Review of missing/outlier handling in wearable-sensor ML pipelines:
  https://pmc.ncbi.nlm.nih.gov/articles/PMC10256016/
- Garmin Venu 2 Body Battery (0-100; based on HRV/stress/sleep/activity):
  https://www8.garmin.com/manuals/webhelp/GUID-D93137A9-B374-4A24-8A4D-A66C9AC91265/EN-US/Venu_2_2S_OM_EN-US.pdf
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

import numpy as np
import pandas as pd


HORIZONS_MIN = {"30m": 30, "1h": 60, "3h": 180, "6h": 360}
CURRENT_BB_MAX_AGE_MIN = 10
TARGET_BB_TOLERANCE_MIN = 3
SHORT_SENSOR_FFILL_ROWS = 2  # 2 x 5-minute bins = at most 10 minutes, causal only
TRAIN_FRACTION = 0.70
VALIDATION_FRACTION = 0.15

# Predictors intentionally selected from the current BioTwin 5-minute master table.
# Old/interpolated Body Battery audit/target columns are NOT in this list.
SAFE_PREDICTORS = [
    # Intraday heart rate
    "hr_mean", "hr_min", "hr_max", "hr_std", "hr_last", "hr_count", "hr_slope_per_min",
    # Intraday stress
    "stress_mean", "stress_min", "stress_max", "stress_std", "stress_last", "stress_count", "stress_slope_per_min",
    # Intraday respiration
    "resp_mean", "resp_min", "resp_max", "resp_std", "resp_last", "resp_count", "resp_slope_per_min",
    # Circadian / day context
    "hour_sin", "hour_cos", "dow_sin", "dow_cos",
    # Completed sleep context
    "sleep_duration_min", "nap_duration_min", "deep_sleep_min", "light_sleep_min", "rem_sleep_min",
    "awake_sleep_min", "sleep_score", "sleep_avg_stress", "sleep_avg_respiration",
    "sleep_low_respiration", "sleep_high_respiration", "sleep_body_battery_change",
    "sleep_resting_hr", "hours_since_sleep_end",
    # Previous completed day summary (causal)
    "prevday_steps", "prevday_distance_m", "prevday_total_kcal", "prevday_active_kcal",
    "prevday_active_min", "prevday_highly_active_min", "prevday_sedentary_min",
    "prevday_moderate_intensity_min", "prevday_vigorous_intensity_min",
    "prevday_floors_ascended", "prevday_resting_hr", "prevday_7d_resting_hr",
    "prevday_avg_stress", "prevday_high_stress_pct", "prevday_medium_stress_pct",
    "prevday_low_stress_pct", "prevday_bb_charged", "prevday_bb_drained",
    "prevday_bb_high", "prevday_bb_low", "prevday_bb_last", "prevday_avg_spo2",
    "prevday_low_spo2", "prevday_waking_respiration", "hours_since_prevday_summary",
    # Workout / activity context
    "workout_active", "workout_type", "last_workout_type", "last_workout_duration_min",
    "last_workout_calories", "last_workout_steps", "last_workout_avg_hr", "last_workout_max_hr",
    "last_workout_distance_m", "last_workout_bb_change", "last_workout_moderate_min",
    "last_workout_vigorous_min", "minutes_since_last_workout",
    # Causal rolling features already built from past/current sensor windows
    "hr_mean_1h", "hr_mean_3h", "stress_mean_1h", "stress_mean_3h",
    "resp_mean_1h", "resp_mean_3h",
]

# Columns that can safely be forward-filled a very short distance for the convenience
# imputed table. We never back-fill because that would use future information.
SHORT_FFILL_PREFIXES = ("hr_", "stress_", "resp_")

# Hard validity rules only. These are deliberately broad; we do not remove legitimate
# physiological extremes based on z-scores/IQR computed from the full dataset.
DOMAIN_RANGES: Dict[str, Tuple[float, float]] = {
    # Sensor ranges
    "hr_mean": (25, 250), "hr_min": (25, 250), "hr_max": (25, 250), "hr_last": (25, 250),
    "stress_mean": (0, 100), "stress_min": (0, 100), "stress_max": (0, 100), "stress_last": (0, 100),
    "resp_mean": (4, 60), "resp_min": (4, 60), "resp_max": (4, 60), "resp_last": (4, 60),
    # Sleep / daily summary
    "sleep_duration_min": (0, 960), "nap_duration_min": (0, 480),
    "deep_sleep_min": (0, 960), "light_sleep_min": (0, 960), "rem_sleep_min": (0, 960),
    "awake_sleep_min": (0, 960), "sleep_score": (0, 100), "sleep_avg_stress": (0, 100),
    "sleep_avg_respiration": (4, 60), "sleep_low_respiration": (4, 60), "sleep_high_respiration": (4, 60),
    "sleep_resting_hr": (25, 250),
    "prevday_steps": (0, 100000), "prevday_distance_m": (0, 200000),
    "prevday_total_kcal": (0, 15000), "prevday_active_kcal": (0, 10000),
    "prevday_active_min": (0, 1440), "prevday_highly_active_min": (0, 1440),
    "prevday_sedentary_min": (0, 1440), "prevday_moderate_intensity_min": (0, 1440),
    "prevday_vigorous_intensity_min": (0, 1440), "prevday_floors_ascended": (0, 1000),
    "prevday_resting_hr": (25, 250), "prevday_7d_resting_hr": (25, 250),
    "prevday_avg_stress": (0, 100), "prevday_high_stress_pct": (0, 100),
    "prevday_medium_stress_pct": (0, 100), "prevday_low_stress_pct": (0, 100),
    "prevday_bb_charged": (0, 100), "prevday_bb_drained": (0, 100),
    "prevday_bb_high": (0, 100), "prevday_bb_low": (0, 100), "prevday_bb_last": (0, 100),
    "prevday_avg_spo2": (50, 100), "prevday_low_spo2": (50, 100),
    "prevday_waking_respiration": (4, 60),
    # Workouts
    "last_workout_duration_min": (0, 600), "last_workout_calories": (0, 10000),
    "last_workout_steps": (0, 100000), "last_workout_avg_hr": (25, 250),
    "last_workout_max_hr": (25, 250), "last_workout_distance_m": (0, 200000),
    "last_workout_bb_change": (-100, 100), "last_workout_moderate_min": (0, 600),
    "last_workout_vigorous_min": (0, 600), "minutes_since_last_workout": (0, 7 * 24 * 60 + 10),
    # Time-since values
    "hours_since_sleep_end": (0, 48), "hours_since_prevday_summary": (0, 48),
}


FEATURE_GROUPS = {
    "hr_": "heart_rate",
    "stress_": "stress",
    "resp_": "respiration",
    "sleep_": "sleep",
    "prevday_": "previous_day",
    "last_workout_": "workout",
    "workout_": "workout",
    "bb_": "body_battery",
    "hour_": "time_context",
    "dow_": "time_context",
    "has_": "data_quality",
    "core_sensor_": "data_quality",
    "row_quality_": "data_quality",
    "missing_": "data_quality",
}


def safe_float(x):
    try:
        if x is None:
            return np.nan
        return float(x)
    except (TypeError, ValueError):
        return np.nan


def load_measured_body_battery(stress_json: Path) -> pd.DataFrame:
    """Extract dense Garmin Body Battery points from stress.json, MEASURED only."""
    with stress_json.open("r", encoding="utf-8") as f:
        days = json.load(f)

    rows: List[Tuple[pd.Timestamp, float]] = []
    status_counts: Dict[str, int] = {}
    for item in days:
        payload = (item or {}).get("data") or {}
        for sample in payload.get("bodyBatteryValuesArray") or []:
            if not isinstance(sample, list) or len(sample) < 3:
                continue
            status = str(sample[1]) if sample[1] is not None else "UNKNOWN"
            status_counts[status] = status_counts.get(status, 0) + 1
            if status != "MEASURED":
                continue
            value = safe_float(sample[2])
            if not np.isfinite(value) or not (0 <= value <= 100):
                continue
            ts = pd.to_datetime(sample[0], unit="ms", utc=True, errors="coerce")
            if pd.isna(ts):
                continue
            rows.append((ts, value))

    if not rows:
        raise RuntimeError(
            "No MEASURED Body Battery values were found in stress.json. "
            "Expected nested data.bodyBatteryValuesArray rows."
        )

    bb = pd.DataFrame(rows, columns=["bb_measured_time", "bb_measured"])
    bb = (
        bb.groupby("bb_measured_time", as_index=False)["bb_measured"]
        .mean()
        .sort_values("bb_measured_time")
        .reset_index(drop=True)
    )
    bb.attrs["status_counts"] = status_counts
    return bb


def attach_measured_body_battery(master: pd.DataFrame, bb: pd.DataFrame) -> pd.DataFrame:
    """Attach causal current BB and measured future targets to each 5-minute row."""
    out = master.sort_values("timestamp_utc").reset_index(drop=True).copy()

    # Current BB: backward-only as-of match => causal, never sees future BB.
    current = pd.merge_asof(
        out[["timestamp_utc"]],
        bb,
        left_on="timestamp_utc",
        right_on="bb_measured_time",
        direction="backward",
        tolerance=pd.Timedelta(minutes=CURRENT_BB_MAX_AGE_MIN),
    )
    out["bb_current_measured"] = current["bb_measured"].to_numpy()
    out["bb_current_age_min"] = (
        (current["timestamp_utc"] - current["bb_measured_time"]).dt.total_seconds() / 60.0
    ).to_numpy()

    # Causal changes: because current BB is already backward-only, these diffs are safe.
    out["bb_current_change_1h"] = out["bb_current_measured"].diff(12)
    out["bb_current_change_3h"] = out["bb_current_measured"].diff(36)

    # Targets: nearest REAL MEASURED Body Battery around the exact future timestamp.
    # No long-gap interpolation. The 3-minute tolerance matches the observed Garmin cadence.
    for label, minutes in HORIZONS_MIN.items():
        query = out[["timestamp_utc"]].copy()
        query["target_time"] = query["timestamp_utc"] + pd.Timedelta(minutes=minutes)
        query["_row_id"] = np.arange(len(query))
        matched = pd.merge_asof(
            query.sort_values("target_time"),
            bb,
            left_on="target_time",
            right_on="bb_measured_time",
            direction="nearest",
            tolerance=pd.Timedelta(minutes=TARGET_BB_TOLERANCE_MIN),
        ).sort_values("_row_id")

        out[f"target_bb_{label}"] = matched["bb_measured"].to_numpy()
        out[f"target_bb_{label}_match_error_min"] = (
            (matched["target_time"] - matched["bb_measured_time"]).abs().dt.total_seconds() / 60.0
        ).to_numpy()

    return out


def clean_domain_invalids(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, int]]:
    out = df.copy()
    invalid_counts: Dict[str, int] = {}

    # Convert infinities to missing first.
    numeric_cols = out.select_dtypes(include=[np.number]).columns
    out[numeric_cols] = out[numeric_cols].replace([np.inf, -np.inf], np.nan)

    for col, (lo, hi) in DOMAIN_RANGES.items():
        if col not in out.columns:
            continue
        x = pd.to_numeric(out[col], errors="coerce")
        bad = x.notna() & ((x < lo) | (x > hi))
        invalid_counts[col] = int(bad.sum())
        out.loc[bad, col] = np.nan

    # Generic count/std sanity checks.
    for col in [c for c in out.columns if c.endswith("_count")]:
        x = pd.to_numeric(out[col], errors="coerce")
        bad = x.notna() & (x < 0)
        invalid_counts[col] = invalid_counts.get(col, 0) + int(bad.sum())
        out.loc[bad, col] = np.nan

    for col in [c for c in out.columns if c.endswith("_std")]:
        x = pd.to_numeric(out[col], errors="coerce")
        bad = x.notna() & (x < 0)
        invalid_counts[col] = invalid_counts.get(col, 0) + int(bad.sum())
        out.loc[bad, col] = np.nan

    return out, invalid_counts


def add_quality_features(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["has_hr"] = out.get("hr_mean", pd.Series(np.nan, index=out.index)).notna().astype(int)
    out["has_stress"] = out.get("stress_mean", pd.Series(np.nan, index=out.index)).notna().astype(int)
    out["has_resp"] = out.get("resp_mean", pd.Series(np.nan, index=out.index)).notna().astype(int)
    out["has_sleep_context"] = out.get("sleep_duration_min", pd.Series(np.nan, index=out.index)).notna().astype(int)
    out["has_prevday_context"] = out.get("prevday_steps", pd.Series(np.nan, index=out.index)).notna().astype(int)
    out["has_current_bb"] = out["bb_current_measured"].notna().astype(int)
    out["core_sensor_count"] = out[["has_hr", "has_stress", "has_resp"]].sum(axis=1)

    # Interpretable quality score (not a target and not based on future values).
    out["row_quality_score"] = (
        0.30 * out["has_current_bb"]
        + 0.15 * out["has_hr"]
        + 0.15 * out["has_stress"]
        + 0.15 * out["has_resp"]
        + 0.15 * out["has_sleep_context"]
        + 0.10 * out["has_prevday_context"]
    ).round(3)
    out["row_quality_tier"] = pd.cut(
        out["row_quality_score"],
        bins=[-np.inf, 0.60, 0.80, np.inf],
        labels=["low", "medium", "high"],
        right=False,
    ).astype("string")
    return out


def assign_chronological_splits(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict[str, object]]:
    out = df.copy()

    # Split at the day level so adjacent 5-minute rows from one day never land in
    # different model sets.
    date_series = pd.to_datetime(out["garmin_calendar_date"], errors="coerce").dt.date
    usable_dates = sorted(
        d for d in date_series[out["bb_current_measured"].notna()].dropna().unique()
    )
    if len(usable_dates) < 10:
        raise RuntimeError(f"Only {len(usable_dates)} usable dates found; need at least 10 for a sensible chronological split.")

    n = len(usable_dates)
    n_train = max(1, int(math.floor(n * TRAIN_FRACTION)))
    n_val = max(1, int(math.floor(n * VALIDATION_FRACTION)))
    if n_train + n_val >= n:
        n_val = 1
        n_train = n - 2

    train_dates = set(usable_dates[:n_train])
    val_dates = set(usable_dates[n_train:n_train + n_val])
    test_dates = set(usable_dates[n_train + n_val:])

    def split_for_date(d):
        if d in train_dates:
            return "train"
        if d in val_dates:
            return "validation"
        if d in test_dates:
            return "test"
        return "outside"

    out["split"] = [split_for_date(d) for d in date_series]

    first_val_date = usable_dates[n_train]
    first_test_date = usable_dates[n_train + n_val]
    val_start = out.loc[date_series == first_val_date, "timestamp_utc"].min()
    test_start = out.loc[date_series == first_test_date, "timestamp_utc"].min()

    # Base quality requirement. We keep a broad but defensible set: current measured BB,
    # at least two of three dense sensor modalities, and at least one recovery/context block.
    base_quality = (
        out["bb_current_measured"].notna()
        & (out["bb_current_age_min"] <= CURRENT_BB_MAX_AGE_MIN)
        & (out["core_sensor_count"] >= 2)
        & ((out["has_sleep_context"] == 1) | (out["has_prevday_context"] == 1))
        & (out["row_quality_score"] >= 0.60)
        & out["split"].isin(["train", "validation", "test"])
    )

    for label, minutes in HORIZONS_MIN.items():
        target_time = out["timestamp_utc"] + pd.Timedelta(minutes=minutes)
        same_split_window = pd.Series(True, index=out.index)
        same_split_window.loc[out["split"] == "train"] = target_time.loc[out["split"] == "train"] < val_start
        same_split_window.loc[out["split"] == "validation"] = target_time.loc[out["split"] == "validation"] < test_start

        out[f"eligible_{label}"] = (
            base_quality
            & out[f"target_bb_{label}"].notna()
            & (out[f"target_bb_{label}_match_error_min"] <= TARGET_BB_TOLERANCE_MIN)
            & same_split_window
        ).astype(int)

    out["eligible_any"] = out[[f"eligible_{h}" for h in HORIZONS_MIN]].max(axis=1)

    split_info = {
        "usable_date_count": n,
        "train_dates": [str(d) for d in usable_dates[:n_train]],
        "validation_dates": [str(d) for d in usable_dates[n_train:n_train + n_val]],
        "test_dates": [str(d) for d in usable_dates[n_train + n_val:]],
        "validation_start_utc": str(val_start),
        "test_start_utc": str(test_start),
    }
    return out, split_info


def select_training_columns(df: pd.DataFrame) -> Tuple[pd.DataFrame, List[str]]:
    predictors = [c for c in SAFE_PREDICTORS if c in df.columns]

    # Add rebuilt causal BB predictors and quality features.
    predictors += [
        "bb_current_measured", "bb_current_age_min", "bb_current_change_1h", "bb_current_change_3h",
        "has_hr", "has_stress", "has_resp", "has_sleep_context", "has_prevday_context",
        "has_current_bb", "core_sensor_count", "row_quality_score", "row_quality_tier",
    ]
    predictors = list(dict.fromkeys(predictors))

    meta = ["timestamp_utc", "garmin_calendar_date", "local_timestamp", "split"]
    targets = []
    for h in HORIZONS_MIN:
        targets += [
            f"target_bb_{h}", f"target_bb_{h}_match_error_min", f"eligible_{h}"
        ]
    targets += ["eligible_any"]

    keep = [c for c in meta + predictors + targets if c in df.columns]
    out = df.loc[:, keep].copy()

    # Keep only rows usable for at least one horizon. This reduces noise/size without
    # forcing the exact same sample count for every horizon.
    out = out.loc[out["eligible_any"] == 1].reset_index(drop=True)
    return out, predictors


def drop_train_useless_predictors(df: pd.DataFrame, predictors: List[str]) -> Tuple[pd.DataFrame, List[str], Dict[str, str]]:
    """Drop only predictors that TRAIN data shows are unusable; avoids test-set leakage."""
    out = df.copy()
    train = out[out["split"] == "train"]
    dropped: Dict[str, str] = {}
    kept: List[str] = []

    for col in predictors:
        if col not in out.columns:
            continue
        s = train[col]
        missing_rate = float(s.isna().mean())
        if missing_rate >= 0.95:
            dropped[col] = f">=95% missing in train ({missing_rate:.1%})"
            continue
        nonmissing = s.dropna()
        if len(nonmissing) == 0:
            dropped[col] = "all missing in train"
            continue
        if nonmissing.nunique(dropna=True) <= 1:
            dropped[col] = "constant in train"
            continue
        kept.append(col)

    drop_cols = [c for c in dropped if c in out.columns]
    out = out.drop(columns=drop_cols)
    return out, kept, dropped


def build_imputed_table(clean_df: pd.DataFrame, predictors: List[str]) -> Tuple[pd.DataFrame, Dict[str, object]]:
    """Leakage-safe convenience imputation for non-tree models.

    - short causal forward-fill for dense sensor-derived predictors only
    - all remaining numeric missing values -> TRAIN median
    - categorical missing values -> TRAIN mode, else 'unknown'
    - never fit preprocessing values on validation/test rows
    """
    out = clean_df.copy().sort_values("timestamp_utc").reset_index(drop=True)
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], utc=True)

    # Capture modality-level missingness before imputation; these columns are already in
    # the cleaned table and remain unchanged.
    ffilled_cols: List[str] = []
    for col in predictors:
        if col not in out.columns or not pd.api.types.is_numeric_dtype(out[col]):
            continue
        if col.startswith(SHORT_FFILL_PREFIXES):
            out[col] = out[col].ffill(limit=SHORT_SENSOR_FFILL_ROWS)
            ffilled_cols.append(col)

    train_mask = out["split"] == "train"
    impute_values: Dict[str, object] = {}

    for col in predictors:
        if col not in out.columns:
            continue
        if pd.api.types.is_numeric_dtype(out[col]):
            train_values = pd.to_numeric(out.loc[train_mask, col], errors="coerce")
            median = train_values.median(skipna=True)
            if pd.isna(median):
                # This should be rare after train-useless filtering; 0 is a transparent
                # final fallback and is recorded in the report.
                median = 0.0
            out[col] = pd.to_numeric(out[col], errors="coerce").fillna(float(median))
            impute_values[col] = float(median)
        else:
            train_values = out.loc[train_mask, col].dropna().astype(str)
            mode = train_values.mode()
            fill = str(mode.iloc[0]) if len(mode) else "unknown"
            out[col] = out[col].astype("string").fillna(fill)
            impute_values[col] = fill

    out["timestamp_utc"] = out["timestamp_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out, {"short_forward_filled_columns": ffilled_cols, "train_imputation_values": impute_values}


def infer_feature_group(name: str) -> str:
    for prefix, group in FEATURE_GROUPS.items():
        if name.startswith(prefix):
            return group
    if name in {"workout_type", "minutes_since_last_workout"}:
        return "workout"
    return "other"


def make_manifest(predictors: Iterable[str]) -> pd.DataFrame:
    rows = []
    for p in predictors:
        rows.append({
            "column": p,
            "role": "predictor",
            "group": infer_feature_group(p),
            "causal_at_prediction_time": "yes",
        })
    for h, minutes in HORIZONS_MIN.items():
        rows.append({
            "column": f"target_bb_{h}",
            "role": "target",
            "group": "future_body_battery",
            "causal_at_prediction_time": "no - label only",
        })
        rows.append({
            "column": f"eligible_{h}",
            "role": "training_filter",
            "group": "data_quality",
            "causal_at_prediction_time": "n/a",
        })
    return pd.DataFrame(rows)


def to_iso_strings(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["timestamp_utc"] = pd.to_datetime(out["timestamp_utc"], utc=True, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Build clean leakage-safe BioTwin Garmin training CSVs.")
    parser.add_argument("--master", default="processed_data/garmin_5min_master.csv", help="5-minute master CSV")
    parser.add_argument("--stress-json", default="raw_json/stress.json", help="Garmin stress.json containing dense Body Battery array")
    parser.add_argument("--output", default="processed_data/garmin_5min_training.csv", help="Primary cleaned training CSV")
    parser.add_argument("--imputed-output", default="processed_data/garmin_5min_training_imputed.csv", help="Leakage-safe imputed training CSV")
    parser.add_argument("--report", default="processed_data/garmin_training_cleaning_report.json")
    parser.add_argument("--manifest", default="processed_data/garmin_feature_manifest.csv")
    args = parser.parse_args()

    master_path = Path(args.master)
    stress_path = Path(args.stress_json)
    output_path = Path(args.output)
    imputed_path = Path(args.imputed_output)
    report_path = Path(args.report)
    manifest_path = Path(args.manifest)

    if not master_path.exists():
        raise SystemExit(f"Master CSV not found: {master_path}")
    if not stress_path.exists():
        raise SystemExit(f"stress.json not found: {stress_path}")

    print("Loading 5-minute master CSV...")
    master = pd.read_csv(master_path, low_memory=False)
    if "timestamp_utc" not in master.columns:
        raise SystemExit("Master CSV must contain timestamp_utc")
    master["timestamp_utc"] = pd.to_datetime(master["timestamp_utc"], utc=True, errors="coerce")
    master = master.dropna(subset=["timestamp_utc"]).sort_values("timestamp_utc")
    duplicate_rows = int(master.duplicated("timestamp_utc").sum())
    master = master.drop_duplicates("timestamp_utc", keep="last").reset_index(drop=True)

    print("Extracting dense MEASURED Body Battery from stress.json...")
    bb = load_measured_body_battery(stress_path)
    status_counts = bb.attrs.get("status_counts", {})
    print(f"  MEASURED BB points: {len(bb):,}")
    print(f"  Range: {bb['bb_measured_time'].min()} -> {bb['bb_measured_time'].max()}")

    print("Rebuilding causal current BB + measured future targets...")
    model_df = attach_measured_body_battery(master, bb)

    print("Applying conservative domain-validity cleaning...")
    model_df, invalid_counts = clean_domain_invalids(model_df)
    model_df = add_quality_features(model_df)

    print("Creating chronological train/validation/test split...")
    model_df, split_info = assign_chronological_splits(model_df)

    clean, predictors = select_training_columns(model_df)
    clean, predictors, dropped_predictors = drop_train_useless_predictors(clean, predictors)

    # Reorder after dropping.
    clean = to_iso_strings(clean)

    print("Building leakage-safe imputed convenience table...")
    imputed, imputation_info = build_imputed_table(clean, predictors)

    for p in [output_path, imputed_path, report_path, manifest_path]:
        p.parent.mkdir(parents=True, exist_ok=True)

    clean.to_csv(output_path, index=False)
    imputed.to_csv(imputed_path, index=False)
    make_manifest(predictors).to_csv(manifest_path, index=False)

    report = {
        "input": {
            "master_csv": str(master_path),
            "stress_json": str(stress_path),
            "master_rows_after_timestamp_dedup": int(len(master)),
            "duplicate_timestamps_removed": duplicate_rows,
        },
        "body_battery": {
            "status_counts_seen_in_stress_json": status_counts,
            "measured_points_used": int(len(bb)),
            "measured_start": str(bb["bb_measured_time"].min()),
            "measured_end": str(bb["bb_measured_time"].max()),
            "current_bb_max_age_min": CURRENT_BB_MAX_AGE_MIN,
            "target_match_tolerance_min": TARGET_BB_TOLERANCE_MIN,
            "targets_are_interpolated": False,
        },
        "cleaning": {
            "domain_invalid_values_set_to_nan": {k: v for k, v in invalid_counts.items() if v > 0},
            "statistical_outlier_deletion_used": False,
            "backfill_used": False,
            "dropped_predictors_based_on_train_only": dropped_predictors,
        },
        "split": split_info,
        "output": {
            "clean_training_rows": int(len(clean)),
            "clean_training_columns": int(len(clean.columns)),
            "predictor_count": int(len(predictors)),
            "split_row_counts": {str(k): int(v) for k, v in clean["split"].value_counts().to_dict().items()},
            "eligible_counts": {h: int(clean[f"eligible_{h}"].sum()) for h in HORIZONS_MIN},
            "target_nonmissing_counts": {h: int(clean[f"target_bb_{h}"].notna().sum()) for h in HORIZONS_MIN},
            "clean_csv": str(output_path),
            "imputed_csv": str(imputed_path),
            "manifest_csv": str(manifest_path),
        },
        "imputation": {
            "policy": "short causal forward-fill for dense sensor features, then TRAIN-only median/mode for remaining predictor gaps",
            **imputation_info,
        },
        "matlab_note": (
            "For each horizon, filter eligible_<h> == 1. Use split=='train' for fitting, "
            "split=='validation' for model selection, and split=='test' exactly once for final reporting. "
            "Do not include any target_bb_* or eligible_* column as a predictor."
        ),
    }
    with report_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, default=str)

    print("\nDone.")
    print(f"Clean rows: {len(clean):,}")
    print(f"Predictors: {len(predictors):,}")
    print("Split rows:", clean["split"].value_counts().to_dict())
    for h in HORIZONS_MIN:
        print(f"Eligible {h}: {int(clean[f'eligible_{h}'].sum()):,}")
    print(f"\nSaved clean:   {output_path.resolve()}")
    print(f"Saved imputed: {imputed_path.resolve()}")
    print(f"Saved report:  {report_path.resolve()}")
    print(f"Saved manifest:{manifest_path.resolve()}")
    print("\nRecommended MATLAB use:")
    print("  - Tree/ensemble models: start with garmin_5min_training.csv; keep NaNs or enable surrogate splits.")
    print("  - Linear/GPR/SVM comparison: use garmin_5min_training_imputed.csv as a fair convenience baseline.")
    print("  - For 1h model: filter eligible_1h == 1, fit on split=train, tune on validation, report test once.")


if __name__ == "__main__":
    main()
