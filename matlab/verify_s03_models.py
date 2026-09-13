#!/usr/bin/env python3
"""Independent port of s03_models.m for the models base MATLAB can express.

Ridge and the Stage 1 baselines are reproduced here and the results written for
commit. The tree ensemble and Gaussian process in s03_models.m need the
Statistics and Machine Learning Toolbox and are NOT reproduced -- scikit-learn is
not installed in this environment, so those rows come only from MATLAB and are
marked as such rather than being guessed at.

Scored on VALIDATION, which makes these numbers comparable to Stage 1 for the
first time. Validation is five days, so it confirms rather than measures: the
precise evidence is the 23-day leave-one-day-out in Stage 2.

The test split stays sealed.

    ./.venv/bin/python matlab/verify_s03_models.py
"""
import collections
import csv
import datetime as dt
import math
import os
import statistics as st

import numpy as np

HORIZONS = [("30m", 30), ("1h", 60), ("3h", 180), ("6h", 360)]
CONTROLS = ["bb_current_measured", "bb_current_change_1h", "hour_sin", "hour_cos"]
RIDGE_LAMBDA = 1.0
BB_MIN, BB_MAX = 0, 100
DATA_CLEAN = "processed_data/garmin_5min_training.csv"
DATA_IMPUTED = "processed_data/garmin_5min_training_imputed.csv"
SELECTED = os.path.join("matlab", "results", "s02_selected_features.csv")
OUTDIR = os.path.join("matlab", "results")


def number(row, key):
    v = row.get(key, "")
    try:
        return float(v) if v not in ("", "NA", "nan", "None") else math.nan
    except ValueError:
        return math.nan


def ridge_fit_predict(Xtr, ytr, Xte, lam=RIDGE_LAMBDA):
    mu = Xtr.mean(axis=0)
    sg = Xtr.std(axis=0, ddof=1)
    sg[(sg == 0) | ~np.isfinite(sg)] = 1.0
    Z = (Xtr - mu) / sg
    ybar = ytr.mean()
    beta = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]), Z.T @ (ytr - ybar))
    return ((Xte - mu) / sg) @ beta + ybar


def score(actual, predicted):
    e = actual - predicted
    sst = float(((actual - actual.mean()) ** 2).sum())
    return {
        "mae": float(np.abs(e).mean()),
        "rmse": float(math.sqrt((e ** 2).mean())),
        "r2": 1 - float((e ** 2).sum()) / sst,
    }


def per_day(actual, predicted, days):
    grouped = collections.defaultdict(lambda: ([], []))
    for a, p, d in zip(actual, predicted, days):
        grouped[d][0].append(a)
        grouped[d][1].append(p)
    return {d: float(np.mean(np.abs(np.array(v[0]) - np.array(v[1]))))
            for d, v in grouped.items()}


def main():
    clean = list(csv.DictReader(open(DATA_CLEAN)))
    imputed = list(csv.DictReader(open(DATA_IMPUTED)))
    selected = list(csv.DictReader(open(SELECTED)))

    added = collections.defaultdict(list)
    for r in selected:
        if r["role"] == "added":
            added[r["horizon"]].append(r["predictor"])

    # has_sleep_context and friends may be text in the raw table; the imputed
    # table is numeric apart from the three binary text columns, which Stage 2
    # encoded. Re-encode identically here.
    for p in list(imputed[0]):
        vals = {r[p] for r in imputed}
        if all(_is_number(v) for v in vals):
            continue
        counts = collections.Counter(r[p] for r in imputed)
        rare = min(counts, key=counts.get)
        for r in imputed:
            r[f"{p}_is_{rare}"] = "1" if r[p] == rare else "0"

    rows_out = []
    print(f"{'horizon':<8}{'model':<34}{'n':>5}{'MAE':>8}{'RMSE':>8}{'R2':>8}")
    print("-" * 71)

    for name, minutes in HORIZONS:
        target = f"target_bb_{name}"
        eligible = f"eligible_{name}"

        def usable(r):
            return (r[eligible] == "1" and number(r, target) == number(r, target)
                    and number(r, "bb_current_measured") == number(r, "bb_current_measured"))

        tr_idx = [i for i, r in enumerate(clean) if r["split"] == "train" and usable(r)]
        va_idx = [i for i, r in enumerate(clean) if r["split"] == "validation" and usable(r)]

        y_tr = np.array([number(clean[i], target) for i in tr_idx])
        y_va = np.array([number(clean[i], target) for i in va_idx])
        days_va = [clean[i]["garmin_calendar_date"] for i in va_idx]

        # --- Stage 1's best rule, recomputed on exactly these rows ----------
        cur = np.array([number(clean[i], "bb_current_measured") for i in va_idx])
        ch = np.array([0.0 if number(clean[i], "bb_current_change_1h") !=
                       number(clean[i], "bb_current_change_1h")
                       else number(clean[i], "bb_current_change_1h") for i in va_idx])
        extrap = np.clip(cur + ch / 60 * minutes, BB_MIN, BB_MAX)
        delta = dt.timedelta(minutes=minutes)
        by_hour = collections.defaultdict(list)
        for i in tr_idx:
            h = (dt.datetime.fromisoformat(clean[i]["local_timestamp"].strip()) + delta).hour
            by_hour[h].append(number(clean[i], target))
        gm = float(y_tr.mean())
        clock = np.array([
            st.mean(by_hour[(dt.datetime.fromisoformat(clean[i]["local_timestamp"].strip())
                             + delta).hour]) or gm
            if by_hour[(dt.datetime.fromisoformat(clean[i]["local_timestamp"].strip())
                        + delta).hour] else gm
            for i in va_idx])
        rules = {
            "baseline: extrapolation": extrap,
            "baseline: time_of_day": clock,
            "baseline: trend_plus_clock": np.clip((extrap + clock) / 2, BB_MIN, BB_MAX),
        }

        # --- ridge on controls, and controls + the Stage 2 additions --------
        feature_sets = {
            "ridge: controls only": list(CONTROLS),
            f"ridge: controls + {len(added[name])} physiology": CONTROLS + added[name],
        }
        preds = dict(rules)
        pd_store = {}
        for label, cols in feature_sets.items():
            Xtr = np.array([[float(imputed[i][c]) for c in cols] for i in tr_idx])
            Xva = np.array([[float(imputed[i][c]) for c in cols] for i in va_idx])
            preds[label] = np.clip(ridge_fit_predict(Xtr, y_tr, Xva), BB_MIN, BB_MAX)

        best_rule = min(rules, key=lambda k: score(y_va, rules[k])["mae"])
        for label, yhat in preds.items():
            m = score(y_va, yhat)
            pd_store[label] = per_day(y_va, yhat, days_va)
            print(f"{name:<8}{label:<34}{len(y_va):>5}{m['mae']:>8.2f}"
                  f"{m['rmse']:>8.2f}{m['r2']:>8.3f}")
            rows_out.append({"horizon": name, "model": label, "split": "validation",
                             "n": len(y_va), **{k: round(v, 4) for k, v in m.items()}})

        # --- paired comparison, on five days ------------------------------
        ctrl = pd_store["ridge: controls only"]
        phys = pd_store[f"ridge: controls + {len(added[name])} physiology"]
        rule = pd_store[best_rule]
        for label, other in (("vs controls-only ridge", ctrl), (f"vs {best_rule}", rule)):
            diffs = [other[d] - phys[d] for d in sorted(phys)]
            mean_d = st.mean(diffs)
            se_d = st.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
            wins = sum(1 for d in diffs if d > 0)
            print(f"        physiology {label:<28} {mean_d:+6.2f} +/- {se_d:.2f} MAE"
                  f"  better on {wins}/{len(diffs)} days")
            rows_out.append({"horizon": name, "model": f"paired: physiology {label}",
                             "split": "validation", "n": len(diffs),
                             "mae": round(mean_d, 4), "rmse": round(se_d, 4),
                             "r2": f"{wins}/{len(diffs)}"})
        print()

    os.makedirs(OUTDIR, exist_ok=True)
    path = os.path.join(OUTDIR, "s03_models.csv")
    with open(path, "w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=["horizon", "model", "split", "n", "mae", "rmse", "r2"])
        w.writeheader()
        w.writerows(rows_out)
    print(f"wrote {path} ({len(rows_out)} rows)")
    print("\nTree ensemble and Gaussian process rows come from MATLAB only "
          "(Statistics and Machine Learning Toolbox); not reproduced here.")
    return 0


def _is_number(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
