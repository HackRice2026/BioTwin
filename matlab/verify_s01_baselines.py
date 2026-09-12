#!/usr/bin/env python3
"""Independent port of s01_baselines.m: checks its logic and writes the results.

MATLAB Online keeps its output in the cloud drive, so the table every later
result is measured against would not live in the repository. This reproduces the
same computation, asserts it matches figures measured straight from the CSV, and
writes matlab/results/ so the locked baselines are committed alongside the code.

Sample standard deviation (n-1) is used to match MATLAB's std exactly, so the
committed numbers are the ones the script prints.

MATLAB is not installed in every environment this repository is worked in, and a
baseline table that every later result is measured against should not rest on a
script nobody has executed. This reimplements the same computation from the same
CSV and asserts the figures match those measured directly from the data.

    ./.venv/bin/python matlab/verify_01_baselines.py
"""
import collections
import csv
import datetime as dt
import os
import math
import statistics as st
import sys

DATA = "processed_data/garmin_5min_training.csv"
HORIZONS = [("30m", 30), ("1h", 60), ("3h", 180), ("6h", 360)]
EVAL_SPLIT = "validation"
BB_MIN, BB_MAX = 0, 100

# Measured directly from the data before either implementation was written.
EXPECTED_MAE = {
    ("30m", "persistence"): 2.76, ("30m", "extrapolation"): 1.21,
    ("1h", "persistence"): 5.33, ("1h", "extrapolation"): 2.35,
    ("3h", "persistence"): 15.05, ("3h", "extrapolation"): 7.80,
    ("6h", "persistence"): 27.84, ("6h", "extrapolation"): 17.34,
}


def number(row, key):
    value = row.get(key, "")
    try:
        return float(value) if value not in ("", "NA", "nan", "None") else math.nan
    except ValueError:
        return math.nan


def score(actual, predicted):
    errors = [a - b for a, b in zip(actual, predicted)]
    n = len(actual)
    mean = sum(actual) / n
    sst = sum((a - mean) ** 2 for a in actual)
    return {
        "mae": sum(abs(e) for e in errors) / n,
        "rmse": math.sqrt(sum(e * e for e in errors) / n),
        "bias": sum(errors) / n,
        "r2": 1 - sum(e * e for e in errors) / sst,
    }


def main():
    rows = list(csv.DictReader(open(DATA)))
    results, failures = {}, []
    summary_rows, per_day_rows = [], []

    for name, minutes in HORIZONS:
        target, eligible = f"target_bb_{name}", f"eligible_{name}"

        def usable(row):
            return (
                row[eligible] == "1"
                and number(row, target) == number(row, target)
                and number(row, "bb_current_measured") == number(row, "bb_current_measured")
            )

        train = [r for r in rows if r["split"] == "train" and usable(r)]
        evaluate = [r for r in rows if r["split"] == EVAL_SPLIT and usable(r)]
        if len(evaluate) < 30:
            continue

        actual = [number(r, target) for r in evaluate]
        current = [number(r, "bb_current_measured") for r in evaluate]
        days = [r["garmin_calendar_date"] for r in evaluate]
        # A missing hourly change means a flat slope, so extrapolation falls back
        # to persistence on that row rather than guessing a trend.
        change = [number(r, "bb_current_change_1h") for r in evaluate]
        slope = [(0.0 if c != c else c) / 60 for c in change]
        train_mean = sum(number(r, target) for r in train) / len(train)

        # Time-of-day climatology, keyed on the hour the target instant falls in
        # and fitted on train only. Body Battery has a strong daily cycle, so far
        # enough ahead a clock outperforms following the current trend -- which
        # means a model handed hour-of-day can look good without using physiology.
        delta = dt.timedelta(minutes=minutes)
        by_hour = collections.defaultdict(list)
        for r in train:
            by_hour[(dt.datetime.fromisoformat(r["local_timestamp"].strip()) + delta).hour].append(
                number(r, target))
        clock = []
        for r in evaluate:
            h = (dt.datetime.fromisoformat(r["local_timestamp"].strip()) + delta).hour
            clock.append(st.mean(by_hour[h]) if by_hour[h] else train_mean)

        extrap = [min(BB_MAX, max(BB_MIN, c + s * minutes)) for c, s in zip(current, slope)]
        predictions = {
            "daily_mean": [train_mean] * len(actual),
            "persistence": current,
            "extrapolation": extrap,
            "time_of_day": clock,
            "trend_plus_clock": [
                min(BB_MAX, max(BB_MIN, (e + c) / 2)) for e, c in zip(extrap, clock)
            ],
        }

        print(f"\n=== {name} | {EVAL_SPLIT} | n={len(actual)} | target sd={st.stdev(actual):.1f} ===")
        for label, predicted in predictions.items():
            metrics = score(actual, predicted)
            grouped = collections.defaultdict(lambda: ([], []))
            for a, p, day in zip(actual, predicted, days):
                grouped[day][0].append(a)
                grouped[day][1].append(p)
            per_day = [
                sum(abs(a - p) for a, p in zip(*pair)) / len(pair[0]) for pair in grouped.values()
            ]
            print(
                f"  {label:<15}MAE {metrics['mae']:6.2f}  RMSE {metrics['rmse']:6.2f}  "
                f"R2 {metrics['r2']:7.3f}  per-day {st.mean(per_day):5.2f} +/- {st.stdev(per_day) if len(per_day) > 1 else 0.0:.2f}"
            )
            results[(name, label)] = metrics
            summary_rows.append({
                "horizon": name, "minutes": minutes, "baseline": label,
                "n": len(actual), "target_sd": round(st.stdev(actual), 4),
                "mae": round(metrics["mae"], 4), "rmse": round(metrics["rmse"], 4),
                "r2": round(metrics["r2"], 4), "bias": round(metrics["bias"], 4),
                "per_day_mae": round(st.mean(per_day), 4),
                "per_day_sd": round(st.stdev(per_day) if len(per_day) > 1 else 0.0, 4),
            })
            for day, pair in grouped.items():
                per_day_rows.append({
                    "horizon": name, "baseline": label, "day": day,
                    "mae": round(sum(abs(a - p) for a, p in zip(*pair)) / len(pair[0]), 4),
                })

    print(f"\n=== agreement with the figures measured from the data ===")
    for key, expected in EXPECTED_MAE.items():
        got = results[key]["mae"]
        if abs(got - expected) >= 0.02:
            failures.append(f"{key}: expected {expected:.2f}, got {got:.2f}")
        print(f"  {key[0]:<4}{key[1]:<15}{expected:6.2f} vs {got:6.2f}  "
              f"{'OK' if abs(got - expected) < 0.02 else 'MISMATCH'}")

    if failures:
        print("\nMISMATCH:\n  " + "\n  ".join(failures))
        return 1
    outdir = os.path.join("matlab", "results")
    os.makedirs(outdir, exist_ok=True)
    for name, data in (("s01_baselines.csv", summary_rows),
                       ("s01_baselines_per_day.csv", per_day_rows)):
        path = os.path.join(outdir, name)
        with open(path, "w", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(data[0]))
            writer.writeheader()
            writer.writerows(data)
        print(f"  wrote {path} ({len(data)} rows)")

    print("\ns01_baselines.m logic verified against the data")
    return 0


if __name__ == "__main__":
    sys.exit(main())
