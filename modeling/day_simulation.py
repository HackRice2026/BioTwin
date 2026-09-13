"""Scenario engine for the Simulate My Day experience.

The fitted MATLAB trajectory remains the source of truth. What-if scenarios
apply small, deterministic overlays on top of that trajectory and label those
overlays as planning estimates rather than measured causal effects.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from modeling.forecast import trajectory


def _clip(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _clock(value: datetime, timezone: str) -> str:
    return value.astimezone(ZoneInfo(timezone)).strftime("%-I:%M %p")


def _future_points(base):
    current = float(base["current"])
    return [{"horizon_minutes": 0, "value": round(current, 1), "validation_mae": 0.0}] + [
        {
            "horizon_minutes": int(p["horizon_minutes"]),
            "value": float(p["value"]),
            "validation_mae": float(p["validation_mae"]),
        }
        for p in base["points"]
    ]


def _shift(points, drain_by_6h: float, frontload: float = 1.0, recovery: float = 0.0):
    shifted = []
    for p in points:
        horizon = p["horizon_minutes"]
        progress = 0 if horizon <= 0 else min(1.0, horizon / 360)
        drain = drain_by_6h * (progress ** frontload)
        lift = recovery * min(1.0, progress / 0.5)
        shifted.append({**p, "value": round(_clip(p["value"] - drain + lift), 1)})
    return shifted


def _proposal_window(plan, now):
    if not plan:
        return None
    workouts = [p for p in plan.proposals if p.kind == "workout" and p.end > now]
    if workouts:
        return sorted(workouts, key=lambda p: p.start)[0]
    return None


def _scenario(
    scenario_id,
    label,
    summary,
    points,
    window,
    workout,
    evening,
    activity_load,
    confidence="medium",
):
    return {
        "id": scenario_id,
        "label": label,
        "summary": summary,
        "points": points,
        "decision": {
            "best_window": window,
            "workout": workout,
            "evening_state": round(evening, 1),
            "activity_load": activity_load,
        },
        "confidence": confidence,
    }


def simulate_day(history, now, timezone="UTC", plan=None, steps=5000, recovery_minutes=30):
    base = trajectory(history, now, timezone)
    if not base.get("available"):
        return {
            "available": False,
            "reason": base.get("reason", "Waiting for a recent Body Battery reading."),
        }

    steps = max(0, min(10000, int(steps)))
    recovery_minutes = max(10, min(60, int(recovery_minutes)))
    baseline_points = _future_points(base)
    evening = baseline_points[-1]["value"]
    proposal = _proposal_window(plan, now)
    fallback_window = now.astimezone(ZoneInfo(timezone)).replace(hour=17, minute=40, second=0, microsecond=0)
    if fallback_window <= now.astimezone(ZoneInfo(timezone)):
        fallback_window += timedelta(days=1)
    window_label = (
        f"{_clock(proposal.start, timezone)}"
        if proposal
        else fallback_window.strftime("%-I:%M %p")
    )
    workout_label = proposal.title if proposal else "Moderate movement"
    train_horizon = (
        max(0, min(360, int((proposal.start - now).total_seconds() / 60)))
        if proposal
        else min(360, int((fallback_window.astimezone(now.tzinfo) - now).total_seconds() / 60))
    )

    baseline = _scenario(
        "current_plan",
        "Current plan",
        "Your fitted forecast, before changing the day.",
        baseline_points,
        window_label,
        workout_label,
        evening,
        "Moderate",
        "medium" if base["basis"] == "model" else "low",
    )

    step_drain = round(steps / 1000 * 0.72, 2)
    steps_points = _shift(baseline_points, step_drain, frontload=0.85)
    steps_evening = steps_points[-1]["value"]
    steps_workout = "Reduced volume" if step_drain >= 4 else workout_label
    steps_window = (
        "Earlier or lighter"
        if step_drain >= 5 and proposal
        else window_label
    )

    train_now_points = _shift(baseline_points, 9.0, frontload=0.45)
    train_now_evening = train_now_points[-1]["value"]
    train_later_drain = 5.5 if train_horizon <= 180 else 4.5
    train_later_points = []
    for p in baseline_points:
        if p["horizon_minutes"] <= train_horizon:
            train_later_points.append(p)
        else:
            progress = (p["horizon_minutes"] - train_horizon) / max(60, 360 - train_horizon)
            train_later_points.append({**p, "value": round(_clip(p["value"] - train_later_drain * min(1, progress)), 1)})
    recovery_lift = min(4.0, 1.8 + recovery_minutes / 30)
    recovery_points = _shift(baseline_points, 0, recovery=recovery_lift)

    scenarios = [
        baseline,
        _scenario(
            "train_now",
            "Train now",
            "Moves the workout earlier and shows the likely evening cost.",
            train_now_points,
            "Now",
            "Shorter session now",
            train_now_evening,
            "High",
            "low",
        ),
        _scenario(
            "train_best_window",
            f"Train at {window_label}",
            "Keeps the session in the best available window.",
            train_later_points,
            window_label,
            workout_label,
            train_later_points[-1]["value"],
            "Moderate",
            "medium",
        ),
        _scenario(
            "extra_steps",
            f"+{steps:,} steps",
            "Adds walking load to the day and adjusts the workout advice.",
            steps_points,
            steps_window,
            steps_workout,
            steps_evening,
            "High" if step_drain >= 5 else "Moderate",
            "low",
        ),
        _scenario(
            "recovery_break",
            f"{recovery_minutes}-min recovery",
            "Estimates a quiet break before training, capped as a modest planning benefit.",
            recovery_points,
            window_label,
            workout_label,
            recovery_points[-1]["value"],
            "Lower",
            "low",
        ),
    ]

    selected = next(s for s in scenarios if s["id"] == "extra_steps")
    if selected["decision"]["evening_state"] <= evening - 5:
        coach = (
            f"{steps:,} extra steps probably makes tonight a lighter-training day. "
            f"I'd keep the window near {selected['decision']['best_window']}, but cut volume instead of forcing the original intensity."
        )
    else:
        coach = (
            f"{steps:,} extra steps changes the forecast, but not enough to cancel the plan. "
            f"I'd keep {window_label} and watch how your Body Battery is moving."
        )

    return {
        "available": True,
        "generated_at": now.isoformat(),
        "basis": base["basis"],
        "current": base["current"],
        "baseline": baseline,
        "scenarios": scenarios,
        "selected_scenario_id": "extra_steps",
        "controls": {
            "steps": steps,
            "step_min": 0,
            "step_max": 10000,
            "recovery_minutes": recovery_minutes,
        },
        "coach_summary": coach,
        "assumptions": [
            "Baseline comes from the exported MATLAB Body Battery trajectory.",
            "Step, workout, and recovery branches are scenario overlays for planning, not proven causal physiology.",
            "Longer horizons rely more on your hour-of-day rhythm than on fitted physiology.",
        ],
    }
