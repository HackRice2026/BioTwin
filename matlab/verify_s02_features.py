#!/usr/bin/env python3
"""Independent port of s02_features.m: runs the same selection and writes results.

Mirrors the MATLAB exactly -- within-day correlation ranking, redundancy pruning,
leave-one-day-out ridge, and the one-standard-error rule -- so the selection can
be checked and committed without MATLAB installed.

    ./.venv/bin/python matlab/verify_s02_features.py
"""
import collections
import csv
import math
import os
import statistics as st

import numpy as np

HORIZONS = [("30m", 30), ("1h", 60), ("3h", 180), ("6h", 360)]
MAX_FEATURES = 40
REDUNDANT_ABS = 0.90
NEAR_CONSTANT = 0.99
RIDGE_LAMBDA = 1.0
DATA = "processed_data/garmin_5min_training_imputed.csv"
MANIFEST = "processed_data/garmin_feature_manifest.csv"
OUTDIR = os.path.join("matlab", "results")


def ridge_predict(Xtr, ytr, Xte, lam):
    """Ridge on standardised predictors, standardisation fitted on the fold only.

    A probe for comparing feature counts, not a candidate model. Solved through
    the normal equations exactly as the MATLAB backslash does.
    """
    mu = Xtr.mean(axis=0)
    sg = Xtr.std(axis=0, ddof=1)
    sg[(sg == 0) | ~np.isfinite(sg)] = 1.0
    Z = (Xtr - mu) / sg
    ybar = ytr.mean()
    A = Z.T @ Z + lam * np.eye(Z.shape[1])
    beta = np.linalg.solve(A, Z.T @ (ytr - ybar))
    return ((Xte - mu) / sg) @ beta + ybar


def main():
    rows = list(csv.DictReader(open(DATA)))
    manifest = list(csv.DictReader(open(MANIFEST)))
    predictors = [r["column"] for r in manifest if r["role"] == "predictor"]

    # Encode binary text predictors against their rarer level.
    encoded = {}
    for p in list(predictors):
        values = {r[p] for r in rows}
        if all(_is_number(v) for v in values):
            continue
        counts = collections.Counter(r[p] for r in rows)
        rare = min(counts, key=counts.get)
        name = f"{p}_is_{rare}"
        for r in rows:
            r[name] = "1" if r[p] == rare else "0"
        encoded[p] = (name, counts[rare])
        predictors[predictors.index(p)] = name
    for old, (new, n) in encoded.items():
        print(f"encoded {old} -> {new} ({n} of {len(rows)} rows)")

    train = [r for r in rows if r["split"] == "train"]
    print(f"\ntrain: {len(train)} rows, {len({r['garmin_calendar_date'] for r in train})} days")

    # Drop near-constant predictors using train only.
    keep, dropped = [], []
    for p in predictors:
        xs = [float(r[p]) for r in train]
        if len(set(xs)) == 1:
            dropped.append(f"{p} (no variation)")
            continue
        levels = set(xs)
        if len(levels) <= 5:
            share = max(sum(1 for x in xs if x == L) / len(xs) for L in levels)
            if share >= NEAR_CONSTANT:
                dropped.append(f"{p} ({share*100:.0f}% one value)")
                continue
        keep.append(p)
    print(f"predictors: {len(predictors)} -> {len(keep)} after dropping near-constant")
    for d in dropped:
        print(f"  dropped {d}")

    selected_rows, curve_rows = [], []
    for name, _minutes in HORIZONS:
        target = f"target_bb_{name}"
        sub = [r for r in train if r[f"eligible_{name}"] == "1" and _is_number(r[target])]
        y = [float(r[target]) for r in sub]
        days = [r["garmin_calendar_date"] for r in sub]
        X = [[float(r[p]) for p in keep] for r in sub]
        day_list = sorted(set(days))
        print(f"\n=== {name} | train rows {len(y)} | days {len(day_list)} ===")
        if len(day_list) < 6:
            print("  too few days to cross-validate -- skipped")
            continue
        idx = {d: [i for i, dd in enumerate(days) if dd == d] for d in day_list}

        Xa = np.asarray(X, dtype=float)
        ya = np.asarray(y, dtype=float)

        # Rank by within-day |r|, averaged across days, so one long day cannot
        # dominate the ranking.
        score = np.zeros(len(keep))
        for j in range(len(keep)):
            per_day = []
            for d in day_list:
                ii = idx[d]
                if len(ii) < 8:
                    continue
                xd = Xa[ii, j]
                if xd.std() == 0:
                    continue
                c = np.corrcoef(xd, ya[ii])[0, 1]
                if np.isfinite(c):
                    per_day.append(abs(c))
            score[j] = float(np.mean(per_day)) if per_day else 0.0
        order = list(np.argsort(-score))

        # Greedy add, skipping predictors that duplicate a chosen one.
        chosen = []
        for j in order:
            if len(chosen) >= MAX_FEATURES:
                break
            duplicate = False
            for c in chosen:
                r = np.corrcoef(Xa[:, j], Xa[:, c])[0, 1]
                if np.isfinite(r) and abs(r) > REDUNDANT_ABS:
                    duplicate = True
                    break
            if not duplicate:
                chosen.append(int(j))

        mae_mean, mae_se = [], []
        for k in range(1, len(chosen) + 1):
            cols = chosen[:k]
            per_day = []
            for d in day_list:
                te = np.asarray(idx[d])
                tr = np.asarray([i for i in range(len(y)) if days[i] != d])
                if te.size < 8 or tr.size < 50:
                    continue
                yhat = ridge_predict(Xa[np.ix_(tr, cols)], ya[tr],
                                     Xa[np.ix_(te, cols)], RIDGE_LAMBDA)
                per_day.append(float(np.mean(np.abs(ya[te] - yhat))))
            mae_mean.append(st.mean(per_day))
            mae_se.append((st.stdev(per_day) / math.sqrt(len(per_day))) if len(per_day) > 1 else 0.0)

        best = min(mae_mean)
        k_best = mae_mean.index(best)
        threshold = best + mae_se[k_best]
        k_chosen = next(i for i, m in enumerate(mae_mean) if m <= threshold) + 1
        print(f"  best held-out MAE {best:.2f} at k={k_best+1}; "
              f"simplest within 1 SE is k={k_chosen} (MAE {mae_mean[k_chosen-1]:.2f})")
        print(f"  {'kept predictor':<34}{'day |r|':>10}{'cumulative MAE':>16}")
        for i in range(k_chosen):
            j = chosen[i]
            print(f"  {keep[j]:<34}{score[j]:>10.3f}{mae_mean[i]:>16.2f}")
            selected_rows.append({"horizon": name, "rank": i + 1, "predictor": keep[j],
                                  "day_abs_corr": round(score[j], 4),
                                  "cumulative_loo_mae": round(mae_mean[i], 4)})
        for i, (m, s) in enumerate(zip(mae_mean, mae_se), start=1):
            curve_rows.append({"horizon": name, "k": i, "loo_mae": round(m, 4),
                               "loo_se": round(s, 4)})

    os.makedirs(OUTDIR, exist_ok=True)
    for fname, data in (("s02_selected_features.csv", selected_rows),
                        ("s02_selection_curve.csv", curve_rows)):
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


def _ok(c):
    return c == c


if __name__ == "__main__":
    raise SystemExit(main())
