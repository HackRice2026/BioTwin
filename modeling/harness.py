"""Deterministic fitness coaching harness around forecast, plan, and policy."""

from shared.schemas import (
    FitnessHarness,
    HarnessDecision,
    HarnessMetric,
    SimulationOverlay,
    utcnow,
)


def _status(value, good, watch):
    if value is None:
        return "unknown"
    if good(value):
        return "good"
    if watch(value):
        return "watch"
    return "limited"


def _overlaps(start, end, intervals):
    return any(start < busy.end and end > busy.start for busy in intervals)


def _fmt_time(stamp, timezone):
    return stamp.astimezone(timezone).strftime("%H:%M")


def build_harness(state, plan=None, outlook=None, simulation: SimulationOverlay | None = None):
    ready = state.readiness
    latest = state.latest
    state_metrics = [
        HarnessMetric(
            key="readiness",
            label="Readiness",
            value="unknown" if ready.score is None else f"{ready.score:g}",
            status=_status(ready.score, lambda v: v >= 65, lambda v: v >= 45),
        ),
        HarnessMetric(
            key="confidence",
            label="Signal confidence",
            value=f"{ready.confidence:.2f}",
            status=_status(ready.confidence, lambda v: v >= 0.7, lambda v: v >= 0.45),
        ),
        HarnessMetric(
            key="sleep_debt",
            label="Sleep debt",
            value="unknown" if ready.sleep_debt_minutes is None else f"{ready.sleep_debt_minutes:g} min",
            status=_status(
                ready.sleep_debt_minutes,
                lambda v: v <= 45,
                lambda v: v <= 120,
            ),
        ),
        HarnessMetric(
            key="heart_rate",
            label="Latest heart rate",
            value="unknown"
            if latest is None or latest.heart_rate_bpm is None
            else f"{latest.heart_rate_bpm:g} bpm",
            status="good" if latest and latest.heart_rate_bpm is not None else "unknown",
        ),
    ]

    forecast_summary = []
    if outlook and outlook.curve:
        best = max(outlook.curve, key=lambda point: point.value)
        worst = min(outlook.curve, key=lambda point: point.value)
        forecast_summary.extend(
            [
                HarnessMetric(
                    key="best_window",
                    label="Best readiness window",
                    value=f"{_fmt_time(best.time, best.time.tzinfo)} · {best.value:g}",
                    status="good" if best.value >= 65 else "watch" if best.value >= 45 else "limited",
                ),
                HarnessMetric(
                    key="low_window",
                    label="Lowest projected point",
                    value=f"{_fmt_time(worst.time, worst.time.tzinfo)} · {worst.value:g}",
                    status="watch" if worst.value >= 45 else "limited",
                ),
                HarnessMetric(
                    key="forecast_confidence",
                    label="Forecast confidence",
                    value=f"{outlook.confidence:.2f}",
                    status=_status(outlook.confidence, lambda v: v >= 0.45, lambda v: v >= 0.25),
                ),
            ]
        )
    else:
        forecast_summary.append(
            HarnessMetric(
                key="forecast_missing",
                label="Forecast",
                value="waiting for readiness signals",
                status="unknown",
            )
        )

    sleep_debt = ready.sleep_debt_minutes or 0
    score = ready.score
    intensity_cap = (
        "mobility"
        if score is None or score < 45
        else "light"
        if score < 65
        else "moderate"
        if score < 83
        else "vigorous"
    )
    volume_multiplier = 1.0
    if score is None:
        volume_multiplier = 0.7
    elif score < 45 and sleep_debt > 90:
        volume_multiplier = 0.65
    elif score < 65 or sleep_debt > 120:
        volume_multiplier = 0.82

    policy = [
        HarnessDecision(
            key="intensity_cap",
            label="Training intensity cap",
            value=intensity_cap,
            reason="Derived from readiness state before Gemini sees the plan.",
        ),
        HarnessDecision(
            key="volume_multiplier",
            label="Volume multiplier",
            value=f"{volume_multiplier:.2f}x",
            reason="Reduces planned work when readiness or sleep debt is constrained.",
        ),
    ]

    evaluations = []
    if plan and plan.proposals:
        for proposal in plan.proposals:
            duration = int((proposal.end - proposal.start).total_seconds() / 60)
            evaluations.append(
                HarnessDecision(
                    key=f"{proposal.id}.calendar_fit",
                    label=f"{proposal.title} calendar fit",
                    value="pass" if not _overlaps(proposal.start, proposal.end, plan.busy) else "blocked",
                    reason=f"{duration}-minute proposal checked against {len(plan.busy)} busy windows.",
                )
            )
            evaluations.append(
                HarnessDecision(
                    key=f"{proposal.id}.policy_fit",
                    label=f"{proposal.title} policy fit",
                    value=proposal.intensity,
                    reason=f"Planner score {proposal.score:g}; terms {proposal.terms}.",
                )
            )
    elif plan:
        evaluations.append(
            HarnessDecision(
                key="plan.empty",
                label="Plan availability",
                value=plan.calendar_status,
                reason=plan.explanation,
            )
        )

    if simulation and simulation.curve:
        delta = simulation.curve[-1].value - simulation.curve[0].value
        evaluations.append(
            HarnessDecision(
                key=f"scenario.{simulation.scenario}",
                label=f"{simulation.scenario.title()} scenario",
                value=f"{delta:+.1f} bpm over {len(simulation.curve)} points",
                reason=simulation.assumption,
            )
        )

    next_actions = []
    if plan and plan.proposals:
        workout = next((p for p in plan.proposals if p.kind == "workout"), None)
        if workout:
            next_actions.append(f"Recommend {workout.title.lower()} at {workout.start.isoformat()}.")
    if ready.score is None:
        next_actions.append("Collect recent wearable signals before making a training recommendation.")
    if not next_actions:
        next_actions.append("Explain the current readiness and keep monitoring for a better training window.")

    confidence_parts = [ready.confidence]
    if outlook:
        confidence_parts.append(outlook.confidence)
    if plan and plan.calendar_status == "connected":
        confidence_parts.append(0.85)
    elif plan and plan.calendar_status == "demo":
        confidence_parts.append(0.45)
    else:
        confidence_parts.append(0.25)

    return FitnessHarness(
        issued_at=utcnow(),
        state_metrics=state_metrics,
        forecast_summary=forecast_summary,
        policy=policy,
        evaluations=evaluations[:8],
        next_actions=next_actions,
        confidence=round(sum(confidence_parts) / len(confidence_parts), 2),
    )
