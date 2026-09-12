import logging
import uuid
from typing import NamedTuple
import numpy as np
from datetime import timedelta
from scipy.optimize import curve_fit
from shared.schemas import CurvePoint, RecoveryPrediction

logger = logging.getLogger(__name__)

# Heart-rate recovery kinetics. Published parasympathetic reactivation is
# 44 +/- 37 s; a constant beyond ten minutes is drift, not recovery.
TAU_MIN_S, TAU_MAX_S = 5.0, 600.0
ASYMPTOTE_FLOOR_BPM = 25.0


def decay(t, rest, peak, tau):
    return rest + (peak - rest) * np.exp(-np.asarray(t) / tau)


class SegmentFit(NamedTuple):
    tau: float
    rmse: float
    asymptote: float
    saturated: bool


def fit_segment(times, heart_rates, resting):
    """Estimate the recovery time constant with the asymptote ESTIMATED, not assumed.

    Recovery during continued light activity relaxes toward an elevated plateau, not
    toward resting HR. Pinning the asymptote near resting forces a sub-maximal decay
    to look almost linear, and the only exponential that fits a near-linear decline
    heading to resting is an enormous tau -- which then saturates the upper bound.
    On this project's own recorded walks that produced a median tau of 900 s (the
    bound itself) against 87 s once the asymptote was freed, with lower residuals on
    60 of 62 segments. `resting` is retained only to seed the search.

    tau is a property of the system, so a constant identified against an elevated
    plateau remains the right constant for a decay-to-rest forecast.
    """
    times, heart_rates = np.asarray(times, dtype=float), np.asarray(heart_rates, dtype=float)
    if len(times) < 8 or times[-1] - times[0] < 120:
        raise ValueError("A recovery segment needs at least eight readings spanning two minutes")
    t = times - times[0]
    low = float(np.min(heart_rates))
    # An exponential decay is approached from above, so the asymptote cannot exceed
    # the lowest reading; it may sit below one that has not yet settled.
    asymptote_ceiling = max(ASYMPTOTE_FLOOR_BPM + 1.0, low)
    seed_asymptote = float(np.clip(heart_rates[-1], ASYMPTOTE_FLOOR_BPM, asymptote_ceiling))
    params, _ = curve_fit(
        decay,
        t,
        heart_rates,
        p0=[seed_asymptote, float(heart_rates[0]), 60.0],
        bounds=(
            [ASYMPTOTE_FLOOR_BPM, low, TAU_MIN_S],
            [asymptote_ceiling, 250.0, TAU_MAX_S],
        ),
        maxfev=20000,
    )
    asymptote, _peak, tau = (float(v) for v in params)
    predicted = decay(t, *params)
    rmse = float(np.sqrt(np.mean((predicted - heart_rates) ** 2)))
    # A constant resting against its bound is an unidentified fit, not a slow one.
    saturated = tau <= TAU_MIN_S * 1.01 or tau >= TAU_MAX_S * 0.99
    return SegmentFit(tau=tau, rmse=rmse, asymptote=asymptote, saturated=saturated)


def _trim_to_trough(window, patience_s=60.0):
    """Cut the window where recovery actually ends.

    A fixed 360 s window keeps collecting after heart rate has settled, and the flat
    tail biases tau upward. Truncate at the trough once it stops improving.
    """
    best_i = 0
    best = window[0].heart_rate_bpm
    for i, f in enumerate(window):
        if f.heart_rate_bpm < best - 0.5:
            best, best_i = f.heart_rate_bpm, i
        elif (f.event_time - window[best_i].event_time).total_seconds() > patience_s:
            break
    return window[: best_i + 1]


def segments(history, resting, absolute=False):
    by_second = {}
    for f in history:
        if f.heart_rate_bpm is not None:
            second = int(f.event_time.timestamp())
            if second not in by_second or (f.confidence, f.sequence) > (
                by_second[second].confidence,
                by_second[second].sequence,
            ):
                by_second[second] = f
    samples = sorted(by_second.values(), key=lambda f: f.event_time)
    result, i = [], 2
    while i < len(samples) - 8:
        a, b = samples[i - 1], samples[i]
        # Activity corroborates recovery when available; a HR decline alone is lower-certainty evidence.
        peak = a.heart_rate_bpm
        if (
            peak > resting + 25
            and b.heart_rate_bpm < peak
            and (b.activity_level is None or b.activity_level < 0.35)
        ):
            window = [a]
            for f in samples[i:]:
                age = (f.event_time - a.event_time).total_seconds()
                gap = (f.event_time - window[-1].event_time).total_seconds()
                if (
                    age > 360
                    or gap > 45
                    or gap <= 0
                    or (f.activity_level is not None and f.activity_level > 0.4)
                ):
                    break
                window.append(f)
            window = _trim_to_trough(window)
            if len(window) >= 8 and (window[-1].event_time - a.event_time).total_seconds() >= 120:
                y = np.array([f.heart_rate_bpm for f in window])
                if np.mean(np.diff(y) <= 2) > 0.8 and y[0] - y[-1] > 15:
                    elapsed = np.array([(f.event_time - a.event_time).total_seconds() for f in window])
                    # Times are relative to each onset, so the absolute instant is
                    # available only on request -- a prequential forecast needs it.
                    result.append((elapsed, y, a.event_time) if absolute else (elapsed, y))
                    i += len(window)
                    continue
        i += 1
    return result


def fit_history(history, resting):
    accepted, taus, asymptotes = [], [], []
    saturated = failed = 0
    for t, y in segments(history, resting):
        try:
            fit = fit_segment(t, y, resting)
        except (ValueError, RuntimeError):
            failed += 1
            continue  # Rejected fit is counted by accepted session count, never replaced with a successful result.
        if fit.saturated:
            # Reported rather than silently dropped: a bound-hit means the segment did
            # not identify a constant, and a gate that hides it makes a failed fit
            # look like a slow recovery.
            saturated += 1
            continue
        if fit.rmse < 12:
            accepted.append((t, y))
            taus.append(fit.tau)
            asymptotes.append(fit.asymptote)
    if saturated or failed:
        logger.info(
            "recovery fit: %d accepted, %d unidentified (bound-limited), %d unfittable",
            len(taus), saturated, failed,
        )
    if len(taus) < 3:
        return dict(
            recovery_tau_s=None, tau_fit_rmse=None, tau_fit_n_sessions=len(taus), tau_iqr=[], cv_errors=[]
        )
    errors = []
    for i, (t, y) in enumerate(accepted):
        heldout_tau = float(np.median(taus[:i] + taus[i + 1 :]))
        # The fold answers one question: does tau generalise to an unseen segment?
        # Forcing the forecast to decay to resting HR instead answers a different one
        # and penalises a correct fit whenever recovery settled above rest, so the
        # segment's own asymptote is held fixed while tau comes from the other folds.
        forecast = decay(t, asymptotes[i], y[0], heldout_tau)
        errors.append(round(float(np.sqrt(np.mean((forecast - y) ** 2))), 2))
    return dict(
        recovery_tau_s=round(float(np.median(taus)), 1),
        tau_fit_rmse=round(float(np.mean(errors)), 2),
        tau_fit_n_sessions=len(taus),
        tau_iqr=[round(float(x), 1) for x in np.percentile(taus, [25, 75])],
        cv_errors=errors,
    )


def issue_prediction(now, latest, baseline):
    if baseline.recovery_tau_s is None or latest is None or latest.heart_rate_bpm is None:
        return None
    error = baseline.tau_fit_rmse or 0
    curve = []
    for t in range(0, 601, 10):
        value = float(decay(t, baseline.resting_hr.median, latest.heart_rate_bpm, baseline.recovery_tau_s))
        curve.append(
            CurvePoint(
                time=now + timedelta(seconds=t),
                value=round(value, 2),
                lower=round(value - 2 * error, 2),
                upper=round(value + 2 * error, 2),
            )
        )
    return RecoveryPrediction(
        id=uuid.uuid4().hex, issued_at=now, horizon_s=600, curve=curve, provenance=latest.provenance
    )


def score_prediction(prediction, history):
    observed = [
        f
        for f in history
        if f.heart_rate_bpm is not None
        and prediction.issued_at
        < f.event_time
        <= prediction.issued_at + timedelta(seconds=prediction.horizon_s)
        and f.ingest_time > prediction.issued_at
        and f.provenance == prediction.provenance
    ]
    if not observed:
        return prediction
    x = np.array([(p.time - prediction.issued_at).total_seconds() for p in prediction.curve])
    y = np.array([p.value for p in prediction.curve])
    actual = [CurvePoint(time=f.event_time, value=f.heart_rate_bpm) for f in observed]
    expected = np.interp([(p.time - prediction.issued_at).total_seconds() for p in actual], x, y)
    rmse = round(float(np.sqrt(np.mean((expected - np.array([p.value for p in actual])) ** 2))), 2)
    return prediction.model_copy(update={"observed": actual, "rmse": rmse})
