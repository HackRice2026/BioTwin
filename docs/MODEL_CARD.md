# BioTwin model card

**Purpose:** explain adult wearable data and support personal wellness planning. The implementation has not been clinically validated and does not assess symptoms, diagnose conditions, prescribe treatment, or guarantee outcomes.

## Personal baseline

Trailing 28 days; per-day summaries prevent a high-frequency sensor from counting as thousands of independent calibration days. Exponential weighting has a seven-day half-life. Weighted medians/MADs resist outliers. A seven-day shrinkage constant blends limited observations with explicit engineering priors. The display exposes that blend rather than claiming complete personalization after one night.

The starting values (resting HR 65 bpm, RMSSD 45 ms, sleep 450 minutes, respiration 15/min, with specified MADs) are **engineering configuration, not validated population reference ranges**. Adult age alone does not establish a suitable physiological prior for every person. The app does not claim those values define health.

Explicit daily resting-HR measurements take precedence over low-activity HR estimates in baseline estimation. Simultaneous competing measurements are selected by quality/source precedence rather than averaged. Unknown or unprovided RMSSD is absent; SDNN and proprietary composites are not substitutes.

## Readiness

Weighted robust standardized contributions from sleep, HRV, resting HR, and decayed sleep deficit. Initial weights are 0.35 / 0.30 / 0.20 / 0.15, taken from the supplied engineering specification, not learned from outcomes. Available contributions are renormalized, while missing/stale/contested readings reduce confidence. No available readiness signals means no readiness score.

The continuous score is mapped to six states using personal historical percentile cuts blended with initial cuts. State transitions require a three-point dead band and a 90-second minimum dwell. The baseline, score, readiness state, and confidence are different concepts; the UI displays them separately.

## Recovery

Automatic segmentation finds an elevated local peak followed by a sustained decline and falling/low activity when available. Segments require eight samples and at least two minutes; large gaps and resumed activity reject a candidate. Nonlinear fitting estimates the exponential heart-rate recovery constant with resting HR bounded near baseline.

At least three accepted sessions are required for a personal tau. Per-session values are aggregated with a median and IQR. Leave-one-session-out validation fits the remaining sessions' tau and predicts the held-out session; each fold's RMSE is available in the baseline payload. Synthetic identifiability tests recover planted constants within 5%.

Recovery predictions assume activity stops and the fitted relaxation continues. They are issued and stored before their observed samples, and later RMSE is calculated only over overlapping, post-issuance observations with matching provenance. A plotted ±2× held-out-RMSE band is an **error visualization, not a calibrated prediction interval**. A low error on generated data is not evidence of accuracy on this user's watch.

## Planning and simulations

Nap and workout candidates are enumerated at 15-minute increments and ranked by explicit timing/debt terms. No candidate overlaps a busy event; naps finish at least six hours before habitual bedtime; workouts finish at least three hours before bedtime; drained states permit mobility only. These are conservative engineering rules from the supplied specification, not individualized medical recommendations.

Rest/light/exercise simulations use a fitted recovery tau when available, otherwise a declared prior. Their activity-response offsets are fixed illustrative assumptions, not measured intervention effects. Simulated data never overwrites measurements or recorded readiness.

The full-day outlook is a separate experimental projection anchored to current readiness. Its time-of-day shape and waking-time decay are fixed heuristics; it is not supported by the short-horizon recovery validation. It is labeled accordingly in the Daily plan view.

## Limitations

Optical-sensor artifacts, exercise type, medications, motion, irregular sampling, different vendor algorithms, and limited history can all affect these estimates. BioTwin reports data quality and uncertainty rather than inferring a condition. No real user recovery data was supplied during this build, so performance on this user's measurements remains unvalidated.
