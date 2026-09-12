# Locked forecasting baselines

Produced by `matlab/s01_baselines.m`, run in MATLAB Online on the validation
split of `processed_data/garmin_5min_training.csv`. Every model result is
measured against this table, so it is fixed here rather than recomputed.

Reproduce with either:

```
run('matlab/s01_baselines.m')                        % MATLAB
./.venv/bin/python matlab/verify_s01_baselines.py    % independent port
```

The two agree on all 54 reported values.

## The three baselines

No model is involved. Each is a rule using only information available at the
moment of prediction.

| baseline | rule |
|---|---|
| `daily_mean` | predict the train-set average, always |
| `persistence` | predict that Body Battery stays where it is now |
| `extrapolation` | predict current value + recent slope × horizon, clamped to 0–100 |

## Validation results

MAE and RMSE are Body Battery points. R² is against the mean of the evaluated
split, so **a negative R² means the rule is worse than having predicted that
mean**.

| horizon | baseline | n | MAE | RMSE | R² | per-day MAE |
|---|---|---:|---:|---:|---:|---|
| 30m | daily_mean | 812 | 20.28 | 24.23 | −0.015 | 21.71 ± 10.81 |
| 30m | persistence | 812 | 2.76 | 3.54 | 0.978 | 2.51 ± 1.12 |
| 30m | **extrapolation** | 812 | **1.21** | 1.61 | **0.996** | 1.15 ± 0.29 |
| 1h | daily_mean | 791 | 20.29 | 24.23 | −0.016 | 22.02 ± 11.68 |
| 1h | persistence | 791 | 5.33 | 6.79 | 0.920 | 4.83 ± 2.16 |
| 1h | **extrapolation** | 791 | **2.35** | 3.09 | **0.983** | 2.22 ± 0.62 |
| 3h | daily_mean | 716 | 20.20 | 24.01 | −0.011 | 22.30 ± 12.32 |
| 3h | persistence | 716 | 15.05 | 18.61 | 0.392 | 13.42 ± 6.05 |
| 3h | **extrapolation** | 716 | **7.80** | 11.13 | **0.783** | 7.90 ± 3.08 |
| 6h | daily_mean | 601 | 18.76 | 22.14 | −0.009 | 18.53 ± 4.73 |
| 6h | persistence | 601 | 27.84 | 32.78 | −1.212 | 26.21 ± 9.23 |
| 6h | extrapolation | 601 | 17.34 | 26.09 | −0.402 | 19.49 ± 15.34 |

## What this settles

**Persistence is not a fair bar.** Following the current slope is about twice as
accurate at every horizon. A model that beats persistence may have learned
nothing except that slope, so `extrapolation` is the number to beat.

**30 minutes and 1 hour are already solved.** Extrapolation reaches R² 0.996 and
0.983. There is no useful headroom, so a model targeted there cannot demonstrate
much even if it trains well.

**Six hours is where the simple rules fail.** Both persistence (R² −1.212) and
extrapolation (R² −0.402) are worse than predicting the mean, and
extrapolation's per-day error swings 19.49 ± 15.34 — unreliable as well as
inaccurate. Whatever governs Body Battery six hours out is not the current
trend, which is where sleep, accumulated load and time awake have to carry the
forecast.

**Three hours is the middle case**: extrapolation is respectable at R² 0.783 but
leaves 7.8 points of error to attack.

## Reading the error bars

Rows are 5-minute windows, so consecutive rows are highly correlated:

```
train        4491 rows    23 days    ~195 rows/day
validation    812 rows     5 days    ~162 rows/day
test          844 rows     6 days    ~141 rows/day
```

The effective sample size is **days, not rows** — roughly 23 for training. The
per-day column is therefore the honest measure of precision: at six hours its
spread is ±15.34, so a model would have to improve MAE by considerably more than
that before the difference could be called real.

## Held back

The **test split is untouched**. Scoring it during model development would make
it part of development. It is evaluated once, on the final model.

Body Battery is Garmin's proprietary metric and several of its own inputs
(stress, heart rate) are predictors here, so the honest framing is *forecasting
Garmin's Body Battery*, never *predicting energy*.
