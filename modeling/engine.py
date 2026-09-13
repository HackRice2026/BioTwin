from collections import defaultdict
from datetime import timedelta
from zoneinfo import ZoneInfo
import math
import numpy as np
from ingestion.normalizer import METRICS
from shared.schemas import (
    Baseline,
    RobustStat,
    Readiness,
    EnergyState,
    AvatarDrivers,
    MetricQuality,
)
from modeling.recovery import fit_history

PRIOR = {"resting_hr": (65, 6), "hrv_rmssd": (45, 12), "sleep_minutes": (450, 45), "respiration": (15, 2)}
# Resting HR, HRV, sleep and respiration drift, so they are estimated over a short
# trailing window. The recovery time constant is a property of the cardiovascular
# system rather than a daily state, and 28 days of clustered wear frequently holds
# fewer than the three recovery segments a personal constant requires -- so it is
# fitted over a longer history. Widening the short window instead would make today's
# resting heart rate stale.
BASELINE_WINDOW_DAYS = 28
RECOVERY_WINDOW_DAYS = 180
FIELDS = {
    "resting_hr": "resting_hr_bpm",
    "hrv_rmssd": "hrv_rmssd_ms",
    "sleep_minutes": "sleep",
    "respiration": "respiration_brpm",
}
STATES = list(EnergyState)
LABELS = {"sleep": "Sleep", "hrv": "Heart-rate variability", "resting_hr": "Resting heart rate"}


def weighted_quantile(values, weights, p):
    order = np.argsort(values)
    values, weights = np.array(values)[order], np.array(weights)[order]
    return float(np.interp(p, (np.cumsum(weights) - 0.5 * weights) / np.sum(weights), values))


def baseline(history, user_id, now, timezone="UTC", fit=True):
    recovery_history = [
        f for f in history if now - timedelta(days=RECOVERY_WINDOW_DAYS) <= f.event_time <= now
    ]
    history = [f for f in history if now - timedelta(days=BASELINE_WINDOW_DAYS) <= f.event_time <= now]
    stats, days_seen = {}, set()
    for name, metric in FIELDS.items():
        by_day = defaultdict(list)
        explicit_rest_days = {
            f.event_time.astimezone(ZoneInfo(timezone)).date()
            for f in history
            if f.resting_hr_bpm is not None
        }
        best_windows = {}
        for f in history:
            value = getattr(f, metric)
            if (
                value is None
                and name == "resting_hr"
                and f.heart_rate_bpm is not None
                and f.activity_level is not None
                and f.activity_level < 0.1
                and f.event_time.astimezone(ZoneInfo(timezone)).date() not in explicit_rest_days
            ):
                value = f.heart_rate_bpm
            if value is not None:
                day = f.event_time.astimezone(ZoneInfo(timezone)).date()
                window = (day, int(f.event_time.timestamp()) // 60)
                ranking = (f.confidence, SOURCE_PRECEDENCE.get(f.provenance.value, 0), f.sequence)
                if window not in best_windows or ranking > best_windows[window][0]:
                    best_windows[window] = (
                        ranking,
                        value.total_minutes if name == "sleep_minutes" else value,
                    )
        for (day, _), (_, value) in best_windows.items():
            by_day[day].append(value)
        days_seen.update(by_day)
        prior, spread = PRIOR[name]
        n = len(by_day)
        w = n / (n + 7)
        if n:
            values = [float(np.median(v)) for v in by_day.values()]
            weights = [
                2 ** (-max(0, (now.astimezone(ZoneInfo(timezone)).date() - day).days) / 7) for day in by_day
            ]
            med = weighted_quantile(values, weights, 0.5)
            mad = weighted_quantile([abs(v - med) for v in values], weights, 0.5)
            stats[name] = RobustStat(
                median=round(w * med + (1 - w) * prior, 2),
                mad=round(max(0.5, w * mad + (1 - w) * spread), 2),
                p10=round(weighted_quantile(values, weights, 0.1), 2),
                p90=round(weighted_quantile(values, weights, 0.9), 2),
                n_days=n,
            )
        else:
            stats[name] = RobustStat(median=prior, mad=spread, p10=prior - 2 * spread, p90=prior + 2 * spread)
    recovery = fit_history(recovery_history, stats["resting_hr"].median) if fit else {}
    return Baseline(
        user_id=user_id,
        computed_at=now,
        n_observations=len(history),
        shrinkage_weight=round(len(days_seen) / (len(days_seen) + 7), 3),
        **stats,
        **recovery,
    )


# A Connect IQ app reads the watch's own sensors and reports within a minute,
# so it outranks a cloud sync of the same sensor, while a direct Bluetooth
# broadcast -- no phone or app in the path -- still outranks both.
SOURCE_PRECEDENCE = {
    "garmin_ble_live": 6,
    "garmin_ciq_live": 5,
    "garmin_live": 4,
    "fitbit_live": 3,
    "fitbit_backfill": 3,
    "garmin_fit_replay": 2,
}


def reconcile(history, now):
    quality, selected = {}, {}
    for metric in METRICS:
        candidates = [f for f in history if getattr(f, metric) is not None and f.event_time <= now]
        if not candidates:
            continue
        newest = max(f.event_time for f in candidates)
        # Reconcile simultaneous measurements, not a stale daily sample against a new sample.
        window = [
            f
            for f in candidates
            if (newest - f.event_time).total_seconds() <= (60 if metric != "sleep" else 1)
        ]
        by_source = {}
        for f in sorted(window, key=lambda x: (x.event_time, x.sequence)):
            by_source[f.provenance] = f
        window = list(by_source.values())
        best = max(
            window,
            key=lambda f: (
                f.confidence,
                SOURCE_PRECEDENCE.get(f.provenance.value, 0),
                f.event_time,
                f.sequence,
            ),
        )
        val = getattr(best, metric)
        threshold = {
            "heart_rate_bpm": 12,
            "resting_hr_bpm": 8,
            "hrv_rmssd_ms": 15,
            "respiration_brpm": 4,
            "spo2_pct": 3,
            "steps": 500,
            "activity_level": 0.3,
        }.get(metric)
        alternatives = [
            {"source": f.provenance.value, "value": getattr(f, metric)}
            for f in window
            if f != best and threshold is not None and abs(getattr(f, metric) - val) > threshold
        ]
        selected[metric] = val
        quality[metric] = MetricQuality(
            provenance=best.provenance,
            event_time=best.event_time,
            confidence=best.confidence,
            contested=bool(alternatives),
            alternatives=alternatives,
        )
    if not history or not selected:
        return None, quality
    latest = max((f for f in history if f.event_time <= now), key=lambda f: (f.event_time, f.sequence))
    return latest.model_copy(update={**{m: None for m in METRICS}, **selected}), quality


def readiness(
    user_id, history, base, now, quality, latest, previous=None, target_sleep=480, timezone="UTC", scores=()
):
    contributions, available, weights = (
        {},
        {},
        {"sleep": 0.35, "hrv": 0.30, "resting_hr": 0.20, "sleep_debt": 0.15},
    )
    reasons = []
    unreported = set()

    def z(x, stat):
        return max(-5, min(5, 0.6745 * (x - stat.median) / max(stat.mad, 0.5)))

    for key, field, stat, sign in [
        ("sleep", "sleep", base.sleep_minutes, 1),
        ("hrv", "hrv_rmssd_ms", base.hrv_rmssd, 1),
        ("resting_hr", "resting_hr_bpm", base.resting_hr, -1),
    ]:
        q = quality.get(field)
        if q and (now - q.event_time).total_seconds() < 36 * 3600:
            val = getattr(latest, field)
            contributions[key] = round(sign * z(val.total_minutes if field == "sleep" else val, stat), 3)
            available[key] = q.confidence * (0.6 if q.contested else 1)
        elif stat.n_days == 0:
            # Never observed from any connected source: the sensor does not report
            # it, which is a different statement from a reading being late.
            unreported.add(key)
            reasons.append(f"{LABELS[key]} is not reported by this device")
        else:
            reasons.append(f"No recent {key.replace('_', ' ')}")
    sleeps = {}
    for f in history:
        if f.sleep and now - timedelta(days=7) <= f.sleep.end <= now:
            sleeps[f.sleep.end.astimezone(ZoneInfo(timezone)).date()] = f.sleep.total_minutes
    debt = None
    if len(sleeps) >= 3:
        debt = 0
        previous_day = None
        for day, minutes in sorted(sleeps.items()):
            elapsed = (day - previous_day).days if previous_day else 1
            debt = max(0, debt * math.exp(-elapsed / 5) + (target_sleep - minutes))
            previous_day = day
        contributions["sleep_debt"] = round(-min(5, debt / 180), 3)
        available["sleep_debt"] = len(sleeps) / 7
    total_weight = sum(weights[k] for k in contributions)
    score = None
    if total_weight:
        raw = sum(weights[k] * v for k, v in contributions.items()) / total_weight
        score = round(100 / (1 + math.exp(-raw / 1.5)), 1)
    cut_weight = min(1, len(scores) / 60)
    cuts = [
        (1 - cut_weight) * p + cut_weight * float(q)
        for p, q in zip(
            [17, 33, 50, 67, 83],
            np.percentile(scores, [10, 25, 45, 70, 90]) if len(scores) >= 7 else [17, 33, 50, 67, 83],
        )
    ]
    state = STATES[sum(score >= c for c in cuts)] if score is not None else EnergyState.BALANCED
    if previous and previous.score is not None and score is not None:
        old, new = STATES.index(previous.state), STATES.index(state)
        elapsed = (now - previous.computed_at).total_seconds()
        # Caller preserves computed_at as the last transition time for this comparison.
        if (
            elapsed < 90
            or (new > old and score < cuts[min(old, 4)] + 3)
            or (new < old and score > cuts[max(0, old - 1)] - 3)
        ):
            state = previous.state
    # Confidence is measured against what the connected sources can actually
    # report, not against the full weight set. A device that never reports RMSSD
    # otherwise caps confidence at 60% however complete its own measurements are,
    # which reads as missing data rather than an absent sensor. A signal that is
    # merely late or contested still counts against confidence in full.
    achievable = sum(w for k, w in weights.items() if k not in unreported) or 1
    confidence = round(
        sum(weights[k] * available[k] for k in available)
        / achievable
        * (0.4 + 0.6 * base.shrinkage_weight),
        2,
    )
    return Readiness(
        user_id=user_id,
        computed_at=now,
        score=score,
        state=state,
        contributions=contributions,
        confidence=confidence,
        degraded_reason="; ".join(reasons) or None,
        sleep_debt_minutes=round(debt, 1) if debt is not None else None,
        cuts=[round(x, 1) for x in cuts],
    )


def drivers(latest, ready, base, quality, now):
    if latest is None:
        return AvatarDrivers(fatigue=0, exertion=0, recovery_progress=0)
    hr, resp, exertion = latest.heart_rate_bpm, latest.respiration_brpm, latest.activity_level
    if "heart_rate_bpm" in quality and (now - quality["heart_rate_bpm"].event_time).total_seconds() > 300:
        hr = None
    if "respiration_brpm" in quality and (now - quality["respiration_brpm"].event_time).total_seconds() > 300:
        resp = None  # Nightly respiratory summaries are displayed as nightly, never animated as live breaths.
    if exertion is None or (now - quality["activity_level"].event_time).total_seconds() > 300:
        exertion = max(0, min(1, (hr - base.resting_hr.median) / 90)) if hr else 0
    fatigue = 1 - ready.score / 100 if ready.score is not None else 0
    progress = max(0, min(1, 1 - (hr - base.resting_hr.median) / 70)) if hr else 0
    return AvatarDrivers(
        pulse_hz=hr / 60 if hr is not None else None,
        breath_hz=resp / 60 if resp is not None else None,
        fatigue=fatigue,
        exertion=exertion,
        recovery_progress=progress,
    )

