from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from modeling.training_window import best_training_window, model_details
from shared.schemas import BusyInterval, EnergyState, TwinState

TZ = ZoneInfo("America/Chicago")
PROFILE = {"timezone": "America/Chicago", "bedtime": "23:00", "workout_minutes": 30}


def golden_state(score=72):
    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    return state.model_copy(
        update={
            "readiness": state.readiness.model_copy(
                update={"score": score, "state": EnergyState.BALANCED, "confidence": 0.8}
            )
        }
    )


def rising_trajectory(current=40):
    return {
        "available": True,
        "basis": "model",
        "current": current,
        "measured_age_minutes": 3,
        "imputed_inputs": [],
        "measured": [],
        "points": [
            {"horizon_minutes": 60, "value": current + 6, "validation_mae": 1.91, "method": "ridge", "beats_baseline": True},
            {"horizon_minutes": 180, "value": current + 20, "validation_mae": 5.2, "method": "trend_plus_clock", "beats_baseline": False},
            {"horizon_minutes": 360, "value": current + 10, "validation_mae": 7.37, "method": "time_of_day", "beats_baseline": False},
        ],
    }


def busy(now, start_h, end_h, title="Meeting"):
    day = now.replace(hour=0, minute=0)
    return BusyInterval(start=day + timedelta(hours=start_h), end=day + timedelta(hours=end_h), title=title)


def test_window_avoids_busy_time_with_transition_buffer():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
    meetings = [busy(now, 13, 14), busy(now, 14.5, 16.75, "Planning review")]
    result = best_training_window(golden_state(), rising_trajectory(), meetings, PROFILE, now, "connected")
    assert result["available"]
    start = datetime.fromisoformat(result["window"]["start"])
    end = start + timedelta(minutes=30)
    for meeting in meetings:
        assert end + timedelta(minutes=10) <= meeting.start or start >= meeting.end + timedelta(minutes=10)
    assert end <= datetime(2026, 9, 14, 20, 0, tzinfo=TZ)


def test_asked_overnight_the_window_waits_until_after_waking():
    now = datetime(2026, 9, 14, 2, 30, tzinfo=TZ)
    result = best_training_window(golden_state(), rising_trajectory(85), [], PROFILE, now, "demo")
    assert datetime.fromisoformat(result["window"]["start"]) >= datetime(2026, 9, 14, 7, 0, tzinfo=TZ)
    assert all(s["key"] != "now" for s in result["scenarios"])
    assert datetime.fromisoformat(result["curve"][-1]["time"]) >= datetime(2026, 9, 14, 20, 0, tzinfo=TZ)


def test_stale_reading_starts_the_day_from_the_measured_value():
    now = datetime(2026, 9, 14, 1, 0, tzinfo=TZ)
    stale = {**rising_trajectory(28), "basis": "rhythm"}
    result = best_training_window(golden_state(), stale, [], PROFILE, now, "demo")
    assert result["now"]["energy"] == 28
    assert result["curve"][0]["value"] == 28
    assert abs(result["curve"][-1]["value"] - result["curve"][-2]["value"]) < 10


def test_window_is_unavailable_without_any_forecast_basis():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
    result = best_training_window(
        golden_state(), {"available": False, "reason": "No Body Battery reading."}, [], PROFILE, now, "connected"
    )
    assert result == {**result, "available": False, "reason": "No Body Battery reading."}
    assert "window" not in result


def test_no_window_after_bedtime_cutoff_still_returns_the_day():
    now = datetime(2026, 9, 14, 19, 50, tzinfo=TZ)
    result = best_training_window(golden_state(), rising_trajectory(), [], PROFILE, now, "connected")
    assert not result["available"]
    assert "20:00" in result["reason"]
    assert result["curve"]


def test_scenarios_rest_keeps_more_evening_energy_than_training():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
    result = best_training_window(golden_state(), rising_trajectory(), [], PROFILE, now, "connected")
    options = {s["key"]: s for s in result["scenarios"]}
    assert options["rest"]["evening_energy"] >= options["best"]["evening_energy"]
    assert sum(s["recommended"] for s in result["scenarios"]) == 1


def test_high_load_window_needs_both_busy_time_and_falling_energy():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
    falling = rising_trajectory(70)
    falling["points"][1]["value"] = 45
    meetings = [busy(now, 14, 14.5), busy(now, 15, 15.75)]
    result = best_training_window(golden_state(), falling, meetings, PROFILE, now, "connected")
    assert result["risks"]
    assert "2 calendar events" in result["risks"][0]["reasons"]
    quiet = best_training_window(golden_state(), falling, [], PROFILE, now, "connected")
    assert quiet["risks"] == []


def test_low_readiness_caps_intensity_regardless_of_energy():
    now = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
    result = best_training_window(golden_state(score=50), rising_trajectory(80), [], PROFILE, now, "connected")
    assert result["window"]["workout"]["intensity"] == "light"


def test_coach_is_grounded_in_the_decision_and_cannot_move_the_window():
    from modeling.explanations import narration_context
    from narration.service import guard

    now = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
    state = golden_state()
    decision = best_training_window(state, rising_trajectory(), [busy(now, 13, 14)], PROFILE, now, "connected")
    ctx = narration_context(state, decision=decision)
    start = datetime.fromisoformat(decision["window"]["start"]).strftime("%I:%M %p").lstrip("0")
    assert start in ctx.coach_brief["recommendation"]
    assert guard(f"Your best window starts at {start}.", ctx, ["coach_brief.recommendation"])
    assert not guard("Your best window starts at 9:15 AM.", ctx, ["coach_brief.recommendation"])


def test_fallback_answers_the_hero_question_and_the_comparison_from_the_decision():
    from modeling.explanations import narration_context
    from narration.service import template

    now = datetime(2026, 9, 14, 12, 0, tzinfo=TZ)
    state = golden_state()
    decision = best_training_window(state, rising_trajectory(), [], PROFILE, now, "connected")
    ctx = narration_context(state, decision=decision)
    start = datetime.fromisoformat(decision["window"]["start"]).strftime("%I:%M %p").lstrip("0")
    assert start in template("When should I work out?", ctx)
    comparison = template("What if I train now?", ctx)
    assert "If you rest instead" in comparison
    assert "not in my current context" not in comparison


def test_training_window_endpoint_requires_sign_in_and_explains_missing_data(tmp_path):
    from fastapi.testclient import TestClient
    from core.api import create_app
    from core.config import Settings

    config = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path}/t.db", demo_enabled=False)
    with TestClient(create_app(config)) as client:
        assert client.get("/api/training-window").status_code == 401
        client.post(
            "/auth/session/register",
            json={"name": "Taylor", "email": "a@example.com", "password": "strong-password-123", "adult": True},
        )
        body = client.get("/api/training-window").json()
    assert body["available"] is False
    assert body["reason"]
    assert len(body["model_details"]) == 3


def test_model_details_report_where_ml_does_not_win():
    rows = {row["horizon"]: row for row in model_details()}
    assert rows["1 hour"]["matlab_mae"] < rows["1 hour"]["baseline_mae"]
    assert not rows["6 hours"]["ml_wins"]
    assert rows["6 hours"]["baseline_mae"] < rows["6 hours"]["matlab_mae"]
