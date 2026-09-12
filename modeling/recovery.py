import uuid
import numpy as np
from datetime import timedelta
from scipy.optimize import curve_fit
from shared.schemas import CurvePoint, RecoveryPrediction


def decay(t, rest, peak, tau):
    return rest + (peak - rest) * np.exp(-np.asarray(t) / tau)


def fit_segment(times, heart_rates, resting):
    times, heart_rates = np.asarray(times, dtype=float), np.asarray(heart_rates, dtype=float)
    if len(times) < 8 or times[-1] - times[0] < 120:
        raise ValueError("A recovery segment needs at least eight readings spanning two minutes")
    t = times - times[0]
    params, _ = curve_fit(
        decay,
        t,
        heart_rates,
        p0=[resting, heart_rates[0], 100],
        bounds=([resting - 5, resting + 5, 15], [resting + 5, 250, 900]),
        maxfev=5000,
    )
    predicted = decay(t, *params)
    return float(params[2]), float(np.sqrt(np.mean((predicted - heart_rates) ** 2)))


def segments(history, resting):
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
            if len(window) >= 8 and (window[-1].event_time - a.event_time).total_seconds() >= 120:
                y = np.array([f.heart_rate_bpm for f in window])
                if np.mean(np.diff(y) <= 2) > 0.8 and y[0] - y[-1] > 15:
                    result.append(
                        (np.array([(f.event_time - a.event_time).total_seconds() for f in window]), y)
                    )
                    i += len(window)
                    continue
        i += 1
    return result


def fit_history(history, resting):
    accepted, taus = [], []
    for t, y in segments(history, resting):
        try:
            tau, rmse = fit_segment(t, y, resting)
        except (ValueError, RuntimeError):
            continue  # Rejected fit is counted by accepted session count, never replaced with a successful result.
        if 16 < tau < 899 and rmse < 12:
            accepted.append((t, y))
            taus.append(tau)
    if len(taus) < 3:
        return dict(
            recovery_tau_s=None, tau_fit_rmse=None, tau_fit_n_sessions=len(taus), tau_iqr=[], cv_errors=[]
        )
    errors = []
    for i, (t, y) in enumerate(accepted):
        heldout_tau = float(np.median(taus[:i] + taus[i + 1 :]))
        forecast = decay(t, resting, y[0], heldout_tau)
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
