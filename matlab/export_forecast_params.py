#!/usr/bin/env python3
"""Fit the 1-hour Body Battery forecast and export it as plain numbers.

Only the features the running app can compute are used. The set MATLAB validated
included resp_mean_1h, which needs an intraday respiration series the app never
ingested; dropping it and adding stress_max scored slightly better on validation
(1.91 against 1.99), and 1.91 also matches the boosted tree MATLAB fitted (1.92)
while beating the best rule (2.35).

That choice was made by comparing four app-computable variants on validation, so
validation is no longer untouched for this model. The sealed test split is the
clean check and is not used here.

Ridge rather than the tree ensemble because a linear model exports as a handful
of numbers the Python runtime evaluates exactly, with no MATLAB at run time --
the same approach used for the recovery constant. MATLAB's backslash and numpy's
solve agreed to 4e-10 on this problem, so fitting here is equivalent.

    ./.venv/bin/python matlab/export_forecast_params.py
"""
import csv
import json
import math
import os

import numpy as np

DATA = "processed_data/garmin_5min_training_imputed.csv"
CLEAN = "processed_data/garmin_5min_training.csv"
OUT = os.path.join("matlab", "params_forecast.json")
HORIZON_MIN = 60
LAMBDA = 1.0
FEATURES = [
    "bb_current_measured",    # the level now
    "bb_current_change_1h",   # which way it is moving
    "hour_sin", "hour_cos",   # what time it is
    "hr_last",                # most recent heart rate
    "has_sleep_context",      # a sleep record exists for the night
    "rem_sleep_min",          # REM minutes from that night
    "stress_max",             # the day's peak stress
]


def value(row, key):
    v = row.get(key, "")
    try:
        return float(v) if v not in ("", "NA", "nan", "None") else math.nan
    except ValueError:
        return math.nan


def main():
    imputed = list(csv.DictReader(open(DATA)))
    clean = list(csv.DictReader(open(CLEAN)))
    target = f"target_bb_{HORIZON_MIN // 60}h"

    def usable(i):
        c = clean[i]
        return (c["eligible_1h"] == "1" and value(c, target) == value(c, target)
                and value(c, "bb_current_measured") == value(c, "bb_current_measured"))

    tr = [i for i in range(len(clean)) if clean[i]["split"] == "train" and usable(i)]
    va = [i for i in range(len(clean)) if clean[i]["split"] == "validation" and usable(i)]

    X = np.array([[value(imputed[i], f) for f in FEATURES] for i in tr])
    y = np.array([value(clean[i], target) for i in tr])
    Xv = np.array([[value(imputed[i], f) for f in FEATURES] for i in va])
    yv = np.array([value(clean[i], target) for i in va])

    mu = X.mean(axis=0)
    sg = X.std(axis=0, ddof=1)
    sg[(sg == 0) | ~np.isfinite(sg)] = 1.0
    Z = (X - mu) / sg
    ybar = float(y.mean())
    beta = np.linalg.solve(Z.T @ Z + LAMBDA * np.eye(Z.shape[1]), Z.T @ (y - ybar))

    pred = np.clip(((Xv - mu) / sg) @ beta + ybar, 0, 100)
    err = yv - pred
    mae = float(np.abs(err).mean())
    rmse = float(math.sqrt((err ** 2).mean()))
    r2 = 1 - float((err ** 2).sum()) / float(((yv - yv.mean()) ** 2).sum())

    params = {
        "model": "ridge",
        "horizon_minutes": HORIZON_MIN,
        "target": "garmin body battery level",
        "features": FEATURES,
        "mean": [round(float(v), 6) for v in mu],
        "std": [round(float(v), 6) for v in sg],
        "coef": [round(float(v), 6) for v in beta],
        "intercept": round(ybar, 6),
        "clip": [0, 100],
        "lambda": LAMBDA,
        "fitted_on": {"rows": len(tr),
                      "days": len({clean[i]["garmin_calendar_date"] for i in tr})},
        "validation": {"rows": len(va), "mae": round(mae, 4),
                       "rmse": round(rmse, 4), "r2": round(r2, 4)},
        "beats": {"best_rule_extrapolation_mae": 2.35,
                  "controls_only_mae": 2.14,
                  "matlab_boosted_trees_mae": 1.92},
        "caveats": [
            "Forecasts Garmin's Body Battery, a proprietary composite, not energy.",
            "Feature set chosen among four app-computable variants on validation, "
            "so validation is not untouched for this model; the test split is.",
            "Fitted on 23 days from one person. Personalised, not validated.",
            "A wellness estimate, not a clinical measurement.",
        ],
    }
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(params, open(OUT, "w"), indent=2)

    print(f"features ({len(FEATURES)}):")
    order = np.argsort(-np.abs(beta))
    for j in order:
        print(f"  {FEATURES[j]:<24} coef {beta[j]:+8.3f}  (standardised)")
    print(f"\nfitted on {len(tr)} rows / {params['fitted_on']['days']} days")
    print(f"validation: MAE {mae:.2f}  RMSE {rmse:.2f}  R2 {r2:.3f}  (n={len(va)})")
    print(f"  vs best rule 2.35 | controls-only 2.14 | MATLAB boosted trees 1.92")
    print(f"\nwrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
