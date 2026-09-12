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

## The five baselines

No model is involved. Each is a rule using only information available at the
moment of prediction.

| baseline | rule |
|---|---|
| `daily_mean` | predict the train-set average, always |
| `persistence` | predict that Body Battery stays where it is now |
| `extrapolation` | current value + recent slope × horizon, clamped to 0–100 |
| `time_of_day` | the train-set average for the hour the target lands in — a clock, with no knowledge of the current state |
| `trend_plus_clock` | the mean of `extrapolation` and `time_of_day` |

## Validation results

MAE and RMSE are Body Battery points. R² is against the mean of the evaluated
split, so **a negative R² means the rule is worse than having predicted that
mean**.

| horizon | baseline | n | MAE | RMSE | R² | per-day MAE |
|---|---|---:|---:|---:|---:|---|
| 30m | daily_mean | 812 | 20.28 | 24.23 | −0.015 | 21.71 ± 10.81 |
| 30m | persistence | 812 | 2.76 | 3.54 | 0.978 | 2.51 ± 1.12 |
| 30m | **extrapolation** | 812 | **1.21** | 1.61 | **0.996** | 1.15 ± 0.30 |
| 30m | time_of_day | 812 | 8.88 | 11.53 | 0.770 | 9.13 ± 1.81 |
| 30m | trend_plus_clock | 812 | 4.38 | 5.63 | 0.945 | 4.56 ± 0.99 |
| 1h | daily_mean | 791 | 20.29 | 24.23 | −0.016 | 22.02 ± 11.68 |
| 1h | persistence | 791 | 5.33 | 6.79 | 0.920 | 4.83 ± 2.16 |
| 1h | **extrapolation** | 791 | **2.35** | 3.09 | **0.983** | 2.22 ± 0.62 |
| 1h | time_of_day | 791 | 8.91 | 11.56 | 0.769 | 9.37 ± 2.12 |
| 1h | trend_plus_clock | 791 | 4.32 | 5.52 | 0.947 | 4.66 ± 1.25 |
| 3h | daily_mean | 716 | 20.20 | 24.01 | −0.011 | 22.30 ± 12.32 |
| 3h | persistence | 716 | 15.05 | 18.61 | 0.392 | 13.42 ± 6.05 |
| 3h | extrapolation | 716 | 7.80 | 11.13 | 0.783 | 7.90 ± 3.08 |
| 3h | time_of_day | 716 | 8.58 | 10.78 | 0.796 | 10.07 ± 4.89 |
| 3h | **trend_plus_clock** | 716 | **5.20** | 6.40 | **0.928** | 5.52 ± 1.30 |
| 6h | daily_mean | 601 | 18.76 | 22.14 | −0.009 | 18.53 ± 4.73 |
| 6h | persistence | 601 | 27.84 | 32.78 | −1.212 | 26.21 ± 9.23 |
| 6h | extrapolation | 601 | 17.34 | 26.09 | −0.402 | 19.49 ± 15.34 |
| 6h | **time_of_day** | 601 | **7.37** | 9.09 | **0.830** | 8.72 ± 4.40 |
| 6h | trend_plus_clock | 601 | 8.34 | 12.75 | 0.665 | 9.21 ± 7.14 |

## What this settles

**The bar changes with the horizon, and a model must beat the best rule at its
own horizon — not the weakest one.**

| horizon | best rule | MAE to beat |
|---|---|---:|
| 30m | extrapolation | 1.21 |
| 1h | extrapolation | 2.35 |
| 3h | trend_plus_clock | 5.20 |
| 6h | time_of_day | 7.37 |

**Persistence is not a fair bar.** Following the current slope is about twice as
accurate at every horizon, so a model that beats persistence may have learned
nothing except that slope.

**A clock is a much harder bar, and it wins outright far ahead.** Body Battery
charges overnight and drains through the day, so the hour is enormously
informative. At six hours a clock with no knowledge of the current state reaches
MAE 7.37 (R² 0.830) while extrapolation manages 17.34 (R² −0.402) — the clock is
2.4× better. **Any model handed `hour_sin`/`hour_cos` can reproduce that without
using physiology at all.**

This was found the hard way. A first feature-selection pass at six hours picked
twelve sleep predictors and stalled at MAE ≈ 23; error only fell, to 10.53, when
the two hour-of-day terms entered. That candidate model would have been beaten
by the clock it was unknowingly imitating.

**30 minutes and 1 hour are already solved.** Extrapolation reaches R² 0.996 and
0.983, so a model targeted there cannot demonstrate much even if it trains well.

**Three hours is the one horizon where combining beats either part**:
trend+clock reaches 5.20 where trend alone gets 7.80 and the clock 8.58. That is
evidence the two carry different information, and it is the most promising place
for a model to add a third source.

**The question Stage 3 must answer** is therefore not "does the model beat
persistence" but: *does adding sleep, load and time-awake improve on trend+clock
at all?* A model given hour-of-day and current Body Battery already has most of
what is predictable here. Anything claimed beyond that has to be demonstrated
against these numbers.

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
