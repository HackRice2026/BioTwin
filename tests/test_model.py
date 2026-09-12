from datetime import datetime, timedelta, timezone
import numpy as np
import pytest
from hypothesis import given, strategies as st
from shared.schemas import TwinFrame, Provenance, Readiness, EnergyState, BusyInterval, SleepSummary
from ingestion.normalizer import normalize
from modeling.recovery import decay, fit_segment, fit_history, issue_prediction, score_prediction
from modeling.engine import baseline, reconcile, readiness, drivers
from modeling.planning import make_plan, overlaps

NOW = datetime(2026, 9, 12, 12, tzinfo=timezone.utc)


def frame(**kwargs):
    return TwinFrame(user_id="u", event_time=NOW, provenance=Provenance.GARMIN_LIVE, **kwargs)


def test_identifiability_recovers_planted_tau():
    rng = np.random.default_rng(0)
    for tau in [45, 110, 220]:
        t = np.arange(0, 361, 5)
        hr = decay(t, 65, 150, tau) + rng.normal(0, 0.2, len(t))
        fit = fit_segment(t, hr, 65)
        assert abs(fit.tau - tau) / tau < 0.05
        assert not fit.saturated


def test_identifiability_recovers_tau_when_recovery_stops_above_resting():
    """Sub-maximal recovery settles on an elevated plateau, not on resting HR.

    Regression test for a pinned asymptote: bounding the asymptote near resting made
    a decay toward 95 bpm unfittable and drove tau into its upper bound. Recorded
    walks in this project produced a median tau of 900 s (the bound) before the fix.
    """
    rng = np.random.default_rng(1)
    for tau, plateau in [(40, 95.0), (70, 120.0), (150, 80.0)]:
        t = np.arange(0, 301, 5)
        hr = decay(t, plateau, 165, tau) + rng.normal(0, 0.3, len(t))
        fit = fit_segment(t, hr, 50)  # resting is 50; the plateau is far above it
        assert abs(fit.tau - tau) / tau < 0.12, f"tau {fit.tau:.0f} vs planted {tau}"
        assert abs(fit.asymptote - plateau) < 6, f"asymptote {fit.asymptote:.0f} vs {plateau}"
        assert not fit.saturated


def test_unidentified_segment_is_reported_not_accepted():
    """A near-linear decline does not identify a constant; it must not pass as a slow one."""
    t = np.arange(0, 301, 5)
    hr = 150 - 0.02 * t  # gentle drift, no exponential settling
    fit = fit_segment(t, hr, 50)
    assert fit.saturated, f"expected a bound-limited fit, got tau {fit.tau:.0f}"


def test_recovery_fit_uses_held_out_sessions():
    history = []
    for day in range(5):
        for second in range(-20, 361, 10):
            hr = 150 + second if second < 0 else float(decay(second, 65, 150, 100 + day * 2))
            history.append(
                frame(heart_rate_bpm=hr, activity_level=0.8 if second <= 0 else 0.02).model_copy(
                    update={"event_time": NOW - timedelta(days=day + 1) + timedelta(seconds=second)}
                )
            )
    fitted = fit_history(sorted(history, key=lambda f: f.event_time), 65)
    assert fitted["tau_fit_n_sessions"] == 5
    assert len(fitted["cv_errors"]) == 5
    assert 0 < fitted["tau_fit_rmse"] < 3


def test_normalizer_dedupes_timezone_equivalence_and_preserves_missing():
    a = frame(heart_rate_bpm=70)
    b = a.model_copy(update={"event_time": NOW.astimezone(timezone(timedelta(hours=-5)))})
    assert normalize(a).dedupe_key == normalize(b).dedupe_key
    assert normalize(a).hrv_rmssd_ms is None
    assert normalize(a.model_copy(update={"heart_rate_bpm": 71})).dedupe_key != normalize(a).dedupe_key
    with pytest.raises(ValueError):
        normalize(frame())
    with pytest.raises(ValueError):
        frame(heart_rate_bpm=400)


def test_baseline_counts_days_not_sampling_frequency():
    a = frame(resting_hr_bpm=60)
    single = baseline([a], "u", NOW)
    many = baseline([a] * 1000, "u", NOW)
    assert single.shrinkage_weight == many.shrinkage_weight
    assert single.resting_hr == many.resting_hr


def test_missing_signals_do_not_become_a_full_confidence_score():
    base = baseline([], "u", NOW)
    ready = readiness("u", [], base, NOW, {}, None)
    assert ready.score is None and ready.confidence == 0
    f = frame(hrv_rmssd_ms=50)
    latest, quality = reconcile([f], NOW)
    ready = readiness("u", [f], base, NOW, quality, latest)
    assert ready.score is not None and ready.confidence < 0.3
    assert "sleep" in ready.degraded_reason.lower()


def test_source_disagreement_is_not_silently_averaged():
    a = frame(heart_rate_bpm=65, confidence=0.9)
    b = frame(heart_rate_bpm=95, confidence=0.7).model_copy(update={"provenance": Provenance.FITBIT_LIVE})
    latest, quality = reconcile([a, b], NOW)
    assert latest.heart_rate_bpm == 65
    assert quality["heart_rate_bpm"].contested
    assert quality["heart_rate_bpm"].alternatives[0]["value"] == 95


def test_stale_respiration_never_becomes_live_breathing():
    old = frame(respiration_brpm=14).model_copy(update={"event_time": NOW - timedelta(hours=5)})
    latest, quality = reconcile([old], NOW)
    base = baseline([old], "u", NOW)
    ready = readiness("u", [old], base, NOW, quality, latest)
    assert drivers(latest, ready, base, quality, NOW).breath_hz is None


def test_hysteresis_holds_state_for_minimum_dwell():
    f = frame(hrv_rmssd_ms=100)
    base = baseline([f], "u", NOW)
    latest, quality = reconcile([f], NOW)
    previous = Readiness(
        user_id="u",
        computed_at=NOW - timedelta(seconds=20),
        score=30,
        state=EnergyState.DRAINED,
        contributions={},
        confidence=0.5,
    )
    ready = readiness("u", [f], base, NOW, quality, latest, previous=previous)
    assert ready.state == EnergyState.DRAINED


@given(
    st.lists(st.tuples(st.integers(0, 23), st.integers(1, 60)), max_size=15),
    st.sampled_from(list(EnergyState)),
)
def test_planner_never_conflicts_or_breaks_hard_constraints(blocks, state):
    now = NOW.replace(hour=7)
    busy = [
        BusyInterval(start=now.replace(hour=h), end=now.replace(hour=h) + timedelta(minutes=m))
        for h, m in blocks
    ]
    ready = Readiness(
        user_id="u",
        computed_at=now,
        score=45,
        state=state,
        contributions={},
        confidence=0.5,
        sleep_debt_minutes=150,
    )
    plan = make_plan(
        now, ready, busy, {"timezone": "UTC", "bedtime": "23:00", "workout_minutes": 30}, "connected"
    )
    for p in plan.proposals:
        assert not overlaps(p.start, p.end, busy)
        if p.kind == "nap":
            assert p.end <= now.replace(hour=17, minute=0)
        if state in [EnergyState.VERY_DRAINED, EnergyState.DRAINED] and p.kind == "workout":
            assert p.intensity == "mobility"
    if len(plan.proposals) == 2:
        assert not overlaps(plan.proposals[0].start, plan.proposals[0].end, plan.proposals[1:])


def test_prediction_scoring_ignores_preissuance_data():
    base = baseline([], "u", NOW).model_copy(update={"recovery_tau_s": 100, "tau_fit_rmse": 2})
    pred = issue_prediction(NOW, frame(heart_rate_bpm=150), base)
    before = frame(heart_rate_bpm=150).model_copy(
        update={"event_time": NOW - timedelta(seconds=1), "ingest_time": NOW + timedelta(seconds=5)}
    )
    assert score_prediction(pred, [before]).rmse is None
    future = frame(heart_rate_bpm=float(decay(10, 65, 150, 100))).model_copy(
        update={"event_time": NOW + timedelta(seconds=10), "ingest_time": NOW + timedelta(seconds=11)}
    )
    assert score_prediction(pred, [before, future]).rmse < 0.02
    assert pred.rmse is None and not pred.observed


def test_sleep_interval_rejects_invalid_duration():
    with pytest.raises(ValueError):
        SleepSummary(start=NOW, end=NOW + timedelta(hours=1), total_minutes=400)
