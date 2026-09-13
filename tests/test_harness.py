from pathlib import Path

from modeling.harness import build_harness
from modeling.outlook import daily_outlook
from shared.schemas import TwinState, utcnow


def test_harness_builds_policy_forecast_and_next_actions():
    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    profile = {"timezone": "UTC", "bedtime": "23:00", "workout_minutes": 30}
    outlook = daily_outlook(state, profile, utcnow())

    harness = build_harness(state, outlook=outlook)

    assert harness.confidence >= 0
    assert {metric.key for metric in harness.state_metrics} >= {
        "readiness",
        "confidence",
        "sleep_debt",
    }
    assert any(metric.key == "best_window" for metric in harness.forecast_summary)
    assert any(decision.key == "intensity_cap" for decision in harness.policy)
    assert harness.next_actions
