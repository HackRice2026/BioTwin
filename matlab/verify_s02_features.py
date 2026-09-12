#!/usr/bin/env python3
"""Independent port of s02_features.m: forward selection against a control model.

A first pass ranked predictors by correlation with the target and, at six hours,
chose twelve sleep features that stalled at MAE ~23 -- the error only fell once
hour-of-day entered, and even then to 10.53, worse than a clock alone (7.37).
Correlation ranking cannot tell a physiological signal from a proxy for the time.

So the controls are forced in and never selected: current Body Battery, its
recent change, and hour-of-day as sine and cosine. Together those reproduce the
trend+clock baseline, which is the strongest rule at every horizon. Candidates
are then ranked by how much they reduce leave-one-DAY-out error when ADDED to
that control model, which is the only question worth asking of them.

TRAIN ONLY, grouped by calendar day throughout: 23 days carry the information,
not 4491 rows.

    ./.venv/bin/python matlab/verify_s02_features.py
"""
import collections
import csv
import math
import os
import statistics as st

import numpy as np

HORIZONS = [("30m", 30), ("1h", 60), ("3h", 180), ("6h", 360)]
CONTROLS = ["bb_current_measured", "bb_current_change_1h", "hour_sin", "hour_cos"]
MAX_ADDED = 12          # candidates added beyond the controls
REDUNDANT_ABS = 0.90
NEAR_CONSTANT = 0.99
RIDGE_LAMBDA = 1.0
DATA = "processed_data/garmin_5min_training_imputed.csv"
MANIFEST = "processed_data/garmin_feature_manifest.csv"
OUTDIR = os.path.join("matlab", "results")


def ridge_predict(Xtr, ytr, Xte, lam=RIDGE_LAMBDA):
    """Ridge on standardised predictors, standardisation fitted on the fold only.

    A probe for comparing feature sets on equal terms, not a candidate model:
    Stage 3 chooses the model.
    """
    mu = Xtr.mean(axis=0)
    sg = Xtr.std(axis=0, ddof=1)
    sg[(sg == 0) | ~np.isfinite(sg)] = 1.0
    Z = (Xtr - mu) / sg
    ybar = ytr.mean()
    beta = np.linalg.solve(Z.T @ Z + lam * np.eye(Z.shape[1]), Z.T @ (ytr - ybar))
    return ((Xte - mu) / sg) @ beta + ybar


def loo_day_mae(X, y, folds, cols):
    """Leave-one-day-out MAE, returned per day so its spread can be reported."""
    per_day = []
    for train_idx, test_idx in folds:
        yhat = ridge_predict(X[np.ix_(train_idx, cols)], y[train_idx],
                             X[np.ix_(test_idx, cols)])
        per_day.append(float(np.mean(np.abs(y[test_idx] - yhat))))
    return per_day


def main():
    rows = list(csv.DictReader(open(DATA)))
    manifest = list(csv.DictReader(open(MANIFEST)))
    predictors = [r["column"] for r in manifest if r["role"] == "predictor"]

    # Encode binary text predictors against their rarer level.
    for p in list(predictors):
        if all(_is_number(r[p]) for r in rows):
            continue
        counts = collections.Counter(r[p] for r in rows)
        rare = min(counts, key=counts.get)
        name = f"{p}_is_{rare}"
        for r in rows:
            r[name] = "1" if r[p] == rare else "0"
        predictors[predictors.index(p)] = name
        print(f"encoded {p} -> {name} ({counts[rare]} of {len(rows)} rows)")

    train = [r for r in rows if r["split"] == "train"]
    print(f"\ntrain: {len(train)} rows, {len({r['garmin_calendar_date'] for r in train})} days")
    for c in CONTROLS:
        assert c in predictors, f"control {c} is not a predictor in the manifest"

    # Drop near-constant predictors on train. Controls are exempt: they are
    # forced in on grounds of what they represent, not their spread.
    keep, dropped = list(CONTROLS), []
    for p in predictors:
        if p in CONTROLS:
            continue
        xs = np.array([float(r[p]) for r in train])
        if xs.std() == 0:
            dropped.append(f"{p} (no variation)")
            continue
        levels = np.unique(xs)
        if levels.size <= 5:
            share = max(float((xs == L).mean()) for L in levels)
            if share >= NEAR_CONSTANT:
                dropped.append(f"{p} ({share * 100:.0f}% one value)")
                continue
        keep.append(p)
    print(f"predictors: {len(predictors)} -> {len(keep)} "
          f"({len(CONTROLS)} controls + {len(keep) - len(CONTROLS)} candidates)")
    for d in dropped:
        print(f"  dropped {d}")

    selected_rows, curve_rows, verdict_rows = [], [], []

    for name, _minutes in HORIZONS:
        target = f"target_bb_{name}"
        sub = [r for r in train
               if r[f"eligible_{name}"] == "1" and _is_number(r[target])]
        y = np.array([float(r[target]) for r in sub])
        days = [r["garmin_calendar_date"] for r in sub]
        X = np.array([[float(r[p]) for p in keep] for r in sub])
        day_list = sorted(set(days))
        print(f"\n=== {name} | train rows {len(y)} | days {len(day_list)} ===")
        if len(day_list) < 6:
            print("  too few days to cross-validate -- skipped")
            continue

        folds = []
        for d in day_list:
            test_idx = np.array([i for i, dd in enumerate(days) if dd == d])
            train_idx = np.array([i for i, dd in enumerate(days) if dd != d])
            if test_idx.size >= 8 and train_idx.size >= 50:
                folds.append((train_idx, test_idx))

        control_cols = [keep.index(c) for c in CONTROLS]
        base_per_day = loo_day_mae(X, y, folds, control_cols)
        base_mae = st.mean(base_per_day)
        base_se = st.stdev(base_per_day) / math.sqrt(len(base_per_day))
        step_per_day = {0: base_per_day}
        print(f"  control model (current BB + change + hour sin/cos): "
              f"MAE {base_mae:.2f} +/- {base_se:.2f}")

        curve_rows.append({"horizon": name, "step": 0, "added": "(controls only)",
                           "loo_mae": round(base_mae, 4), "loo_se": round(base_se, 4),
                           "gain": 0.0})

        chosen, chosen_names = list(control_cols), []
        current_mae, current_se = base_mae, base_se
        candidates = [j for j in range(len(keep)) if keep[j] not in CONTROLS]

        print(f"  {'step':<5}{'added predictor':<34}{'MAE':>8}{'gain':>8}")
        for step in range(1, MAX_ADDED + 1):
            best = None
            for j in candidates:
                # skip anything that duplicates a predictor already in the model
                dup = False
                for c in chosen:
                    r = np.corrcoef(X[:, j], X[:, c])[0, 1]
                    if np.isfinite(r) and abs(r) > REDUNDANT_ABS:
                        dup = True
                        break
                if dup:
                    continue
                per_day = loo_day_mae(X, y, folds, chosen + [j])
                mae = st.mean(per_day)
                if best is None or mae < best[0]:
                    best = (mae, j, per_day)
            if best is None:
                break
            mae, j, per_day = best
            gain = current_mae - mae
            chosen.append(j)
            chosen_names.append(keep[j])
            candidates.remove(j)
            se = st.stdev(per_day) / math.sqrt(len(per_day))
            print(f"  {step:<5}{keep[j]:<34}{mae:>8.2f}{gain:>+8.2f}")
            curve_rows.append({"horizon": name, "step": step, "added": keep[j],
                               "loo_mae": round(mae, 4), "loo_se": round(se, 4),
                               "gain": round(gain, 4)})
            step_per_day[step] = per_day
            current_mae, current_se = mae, se

        # How many additions are justified: the one-standard-error rule against
        # the best point on the curve.
        steps = [r for r in curve_rows if r["horizon"] == name]
        best_row = min(steps, key=lambda r: r["loo_mae"])
        threshold = best_row["loo_mae"] + best_row["loo_se"]
        chosen_step = next(r["step"] for r in steps if r["loo_mae"] <= threshold)

        # Paired comparison: both models are scored on the same held-out days, so
        # the spread that matters is that of the per-day DIFFERENCE, not of either
        # model's own error. Comparing a gain to one model's standard error
        # discards that pairing and understates the evidence in both directions.
        best_per_day = step_per_day[best_row["step"]]
        diffs = [b - a for b, a in zip(base_per_day, best_per_day)]
        mean_diff = st.mean(diffs)
        se_diff = st.stdev(diffs) / math.sqrt(len(diffs)) if len(diffs) > 1 else 0.0
        wins = sum(1 for d in diffs if d > 0)
        ratio = mean_diff / se_diff if se_diff > 0 else float("inf")
        verdict = ("clear" if ratio >= 2 else "suggestive" if ratio >= 1
                   else "not demonstrated")
        improvement = base_mae - best_row["loo_mae"]

        print(f"  best MAE {best_row['loo_mae']:.2f} at step {best_row['step']}; "
              f"simplest within 1 SE is step {chosen_step}")
        print(f"  physiology beyond trend+clock: {mean_diff:+.2f} +/- {se_diff:.2f} MAE "
              f"paired over {len(diffs)} days ({mean_diff/se_diff if se_diff else 0:.1f} SE), "
              f"better on {wins}/{len(diffs)} days -> {verdict.upper()}")

        verdict_rows.append({
            "horizon": name, "control_mae": round(base_mae, 4),
            "control_se": round(base_se, 4),
            "best_mae": round(best_row["loo_mae"], 4),
            "best_step": best_row["step"], "chosen_step": chosen_step,
            "improvement": round(improvement, 4),
            "paired_mean_diff": round(mean_diff, 4),
            "paired_se_diff": round(se_diff, 4),
            "paired_se_ratio": round(ratio, 2) if se_diff > 0 else "",
            "days_improved": f"{wins}/{len(diffs)}",
            "verdict": verdict,
        })
        for i, nm in enumerate(chosen_names[:chosen_step], start=1):
            selected_rows.append({"horizon": name, "rank": i, "predictor": nm,
                                  "role": "added"})
        for c in CONTROLS:
            selected_rows.append({"horizon": name, "rank": 0, "predictor": c,
                                  "role": "control"})

    os.makedirs(OUTDIR, exist_ok=True)
    for fname, data in (("s02_selected_features.csv", selected_rows),
                        ("s02_selection_curve.csv", curve_rows),
                        ("s02_verdict.csv", verdict_rows)):
        path = os.path.join(OUTDIR, fname)
        with open(path, "w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]))
            w.writeheader()
            w.writerows(data)
        print(f"  wrote {path} ({len(data)} rows)")
    return 0


def _is_number(v):
    try:
        float(v)
        return True
    except (TypeError, ValueError):
        return False


if __name__ == "__main__":
    raise SystemExit(main())
