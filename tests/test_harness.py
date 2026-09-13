from pathlib import Path
from datetime import timedelta

import pytest

from modeling.engine import simulate
from modeling.harness import build_harness
from modeling.outlook import daily_outlook
from shared.schemas import BusyInterval, DailyPlan, Proposal, TwinState, utcnow


def test_harness_builds_policy_forecast_and_next_actions():
    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    profile = {"timezone": "UTC", "bedtime": "23:00", "workout_minutes": 30}
    outlook = daily_outlook(state, profile, utcnow())

    harness = build_harness(state, outlook=outlook)

    assert harness.confidence >= 0
    assert {metric.key for metric in harness.state} >= {
        "readiness",
        "confidence",
        "sleep_debt",
    }
    assert any(metric.key == "best_window" for metric in harness.forecast)
    assert any(decision.key == "intensity_cap" for decision in harness.policy_decisions)
    assert harness.next_actions
    assert "explain_plan" in harness.allowed_actions


def test_harness_rejects_plan_that_overlaps_busy_calendar_window():
    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    now = utcnow()
    proposal = Proposal(
        id="p",
        kind="workout",
        title="Light movement",
        start=now,
        end=now + timedelta(minutes=20),
        intensity="light",
        reason="Test proposal",
        score=0.5,
        terms={},
    )
    plan = DailyPlan(
        date=str(now.date()),
        timezone="UTC",
        calendar_status="connected",
        proposals=[proposal],
        busy=[BusyInterval(start=proposal.start, end=proposal.end, title="Meeting")],
        explanation="Test plan",
    )

    with pytest.raises(ValueError, match="overlaps"):
        build_harness(state, plan=plan)


def test_harness_scenario_summary_matches_actual_simulation_curve():
    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    simulation = simulate("light", state, utcnow())
    harness = build_harness(state, simulation=simulation)

    scenario = harness.scenarios[0]
    assert scenario.start_value == round(simulation.curve[0].value, 1)
    assert scenario.peak_value == round(max(point.value for point in simulation.curve), 1)
    assert scenario.end_value == round(simulation.curve[-1].value, 1)
