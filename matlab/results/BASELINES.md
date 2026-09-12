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

---

# Stage 2: does physiology add anything beyond trend and a clock?

Produced by `matlab/s02_features.m`. Leave-one-day-out over the 23 **train**
days only — validation and test are untouched.

Four predictors are forced in and never selected, because together they
reproduce the `trend_plus_clock` baseline above:

```
bb_current_measured     where Body Battery is now
bb_current_change_1h    which way it is moving
hour_sin, hour_cos      what time it is
```

Every other predictor is ranked by how much it reduces held-out error when
**added** to that control model. The verdict is a paired comparison: both models
score the same held-out days, so the evidence is in the spread of the per-day
difference, not in either model's own error.

| horizon | control MAE | best MAE | gain (paired) | SE ratio | days improved | verdict |
|---|---:|---:|---|---:|---:|---|
| 30m | 1.36 | 1.14 | +0.22 ± 0.05 | 4.2 | 21/23 | **clear** |
| 1h | 2.65 | 2.22 | +0.44 ± 0.15 | 3.0 | 20/23 | **clear** |
| 3h | 7.52 | 6.50 | +1.02 ± 0.61 | 1.7 | 17/23 | suggestive |
| 6h | 10.39 | 9.26 | +1.13 ± 0.77 | 1.5 | 17/23 | suggestive |

**Physiology does add something.** The gain is small in absolute terms — about
1.1 Body Battery points at six hours, an 11% reduction — but it is consistent:
better on 17 of 23 days at the long horizons and 21 of 23 at the short ones.

The evidence is **strong at short horizons and only suggestive at long ones**,
which is the opposite of what the project narrative wanted. At 30 minutes and one
hour the gain is 3–4 standard errors; at three and six hours it is 1.5–1.7, so
those cannot be called established on 23 days.

## What each horizon reaches for first

The first predictor chosen at each horizon says what the control model was
missing:

| horizon | first addition | gain |
|---|---|---:|
| 30m | `hr_last` (most recent heart rate) | +0.22 |
| 1h | `hr_last` | +0.21 |
| 3h | `hr_mean` | +0.26 |
| 6h | `has_sleep_context` | +0.30 |

Short horizons reach for the **current heart rate**; six hours reaches for
**whether a sleep record exists**. That the six-hour model's best single addition
is a data-availability flag rather than a physiological quantity is worth
stating plainly — it may be marking "this is a normal day with a recorded night"
rather than measuring recovery.

## How this differs from the first attempt

The first version ranked predictors by correlation with the target. At six hours
it chose twelve sleep features, stalled at MAE ≈ 23, and only improved — to
10.53 — once hour-of-day entered. Since a clock alone reaches 7.37 on validation,
that model would have lost to the thing it was imitating. Correlation ranking
cannot separate a physiological signal from a proxy for the time of day, and
many sleep columns step-change at the sleep boundary, which correlates with the
clock rather than with the body.

## Caveat on comparing the two tables

Stage 1's figures are on **validation**; Stage 2's are leave-one-day-out on
**train**. They are not directly comparable — the Stage 2 control MAE of 10.39 at
six hours cannot be read against Stage 1's clock at 7.37. Stage 3 evaluates on
validation, where the two become comparable for the first time.

---

# Stage 3: which model beats the rules, and where?

Produced by `matlab/s03_models.m`, scored on **validation** — the first numbers
comparable to Stage 1. Validation is five days, so it confirms rather than
measures; the test split remains sealed for one final evaluation.

| horizon | best rule | ridge controls | ridge + physiology | verdict |
|---|---:|---:|---:|---|
| 30m | extrapolation **1.21** | 1.13 | **1.00** | model wins, better on 5/5 days |
| 1h | extrapolation **2.35** | 2.14 | **1.99** | model wins on pooled MAE, marginal per day |
| 3h | trend+clock **5.20** | 6.28 | 6.32 | **rule wins** |
| 6h | time_of_day **7.37** | 8.47 | 9.21 | **rule wins**, model better on only 1/5 days |

## Stage 2's gains did not transfer past one hour

Stage 2 measured leave-one-day-out on the 23 training days and found physiology
helping at every horizon — +1.02 MAE at three hours, +1.13 at six. On held-out
validation days those gains **reverse**: the selected predictors make the model
worse than the ridge without them, and worse than the hand-written rule.

That is selection overfitting, and the cause is the sample size this project has
kept running into. Features were chosen by searching 88 candidates against 23
days; with that many comparisons some will fit those particular days by chance.
The paired train figures at three and six hours were only 1.5–1.7 standard errors
— labelled "suggestive" rather than "clear" for exactly this reason — and
suggestive did not survive.

## Where this data genuinely works

**Thirty minutes.** Ridge with four physiology predictors reaches MAE 1.00
against the best rule's 1.21, and is better on 5 of 5 validation days with a
paired spread of ±0.01. That is a real, held-out, reproducible improvement.

**One hour.** 1.99 against 2.35 pooled, but the paired per-day margin is
+0.04 ± 0.15 against the controls-only ridge. Directionally right, not
established.

**Three and six hours.** The simple rules win. At six hours a clock — the
train-set average Body Battery for each hour of day, with no knowledge of the
current state at all — beats every fitted model tried.

## The claim this supports

> Current heart rate and recent physiology measurably improve short-horizon
> Body Battery forecasting over trend-and-clock extrapolation: MAE 1.21 → 1.00
> at thirty minutes, better on every held-out day.

And the claim it does **not** support: anything about predicting six hours ahead.
The honest six-hour finding is that a clock is hard to beat, which is itself
worth reporting — it says the metric is dominated by circadian shape rather than
by the day's physiology.

## Models still to run

`s03_models.m` also fits bagged trees, boosted trees (LSBoost) and a Gaussian
process on the same predictors, so any difference is the model rather than the
information. Those need the Statistics and Machine Learning Toolbox and are
skipped with a message on a base licence. They are **not** reproduced in
`verify_s03_models.py` — scikit-learn is absent from that environment, and
guessing their numbers would be worse than leaving them blank.

---

# Stage 3, run in MATLAB: the trees change the answer

`s03_models.m` executed in MATLAB Online with the Statistics and Machine
Learning Toolbox. The ridge and baseline rows reproduced the Python verifier
exactly; the three toolbox models had never been run before and they overturn
the conclusion reached from ridge alone.

| horizon | best rule | ridge + physiology | bagged trees | boosted trees | GPR |
|---|---:|---:|---:|---:|---:|
| 1h | extrapolation 2.35 | 1.99 | — | **1.92** | 7.01 |
| 3h | trend+clock 5.20 | 6.32 | **4.84** | 5.35 | 9.20 |
| 6h | **time_of_day 7.37** | 9.21 | 8.47 | 8.91 | 11.16 |

**A linear model was not enough.** Ridge with the same predictors lost to the
rules at three hours (6.32 against 5.20). A bagged tree ensemble on the identical
predictors reaches **4.84** — so the information was there and the linear form
could not use it. That is the clearest MathWorks-specific result in this project:
the model class mattered, not the feature set.

**Boosted trees win at one hour** (1.92 against extrapolation's 2.35 and ridge's
1.99).

**Nothing beats the clock at six hours.** Bagged trees come closest at 8.47
against 7.37. The best six-hour predictor of Body Battery remains the train-set
average for the hour of day, with no knowledge of the current state.

**The Gaussian process fails everywhere** — 7.01, 9.20, 11.16 — despite having
the same predictors. With an ARD squared-exponential kernel on ~4000 correlated
rows from 23 days it is almost certainly over-smoothing; it should not be
presented as a tuned result.

## A limitation in how the verdict was printed

The "physiology vs best rule" line that `s03_models.m` prints compares only the
**ridge** model to the best rule. It therefore reports "the best rule still wins
here" at three hours even though bagged trees beat that rule on the same rows.
The printed verdict is narrower than the table above it, and the table is what
counts. Worth fixing before this is presented.

## Rows still to capture

The 30-minute block and the bagged-trees row at one hour scrolled out of the
captured output. `results/s03_models.csv` in MATLAB Drive holds them.
