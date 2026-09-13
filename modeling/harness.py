"""Deterministic fitness coaching harness around forecast, plan, and policy."""

from shared.schemas import (
    FitnessHarnessResult,
    HarnessDecision,
    HarnessMetric,
    HarnessScenario,
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


def _validate_plan_fits_calendar(plan):
    if not plan:
        return
    for proposal in plan.proposals:
        if proposal.end <= proposal.start:
            raise ValueError("Harness rejected a proposal with non-positive duration")
        if _overlaps(proposal.start, proposal.end, plan.busy):
            raise ValueError("Harness rejected a proposal that overlaps a busy calendar window")


def _scenario_result(simulation: SimulationOverlay | None):
    if not simulation or not simulation.curve:
        return None
    values = [point.value for point in simulation.curve]
    start = values[0]
    peak = max(values)
    end = values[-1]
    delta = round(end - start, 1)
    return HarnessScenario(
        key=simulation.scenario,
        label=f"{simulation.scenario.title()} path",
        start_value=round(start, 1),
        peak_value=round(peak, 1),
        end_value=round(end, 1),
        delta=delta,
        explanation=(
            f"{simulation.scenario.title()} changes the modeled heart-rate path "
            f"from {start:.1f} bpm to {end:.1f} bpm ({delta:+.1f} bpm). "
            f"{simulation.assumption}"
        ),
    )


def build_harness(state, plan=None, outlook=None, simulation: SimulationOverlay | None = None):
    _validate_plan_fits_calendar(plan)
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

    plan_checks = []
    if plan and plan.proposals:
        for proposal in plan.proposals:
            duration = int((proposal.end - proposal.start).total_seconds() / 60)
            plan_checks.append(
                HarnessDecision(
                    key=f"{proposal.id}.calendar_fit",
                    label=f"{proposal.title} calendar fit",
                    value="pass" if not _overlaps(proposal.start, proposal.end, plan.busy) else "blocked",
                    reason=f"{duration}-minute proposal checked against {len(plan.busy)} busy windows.",
                )
            )
            plan_checks.append(
                HarnessDecision(
                    key=f"{proposal.id}.policy_fit",
                    label=f"{proposal.title} policy fit",
                    value=proposal.intensity,
                    reason=f"Planner score {proposal.score:g}; terms {proposal.terms}.",
                )
            )
    elif plan:
        plan_checks.append(
            HarnessDecision(
                key="plan.empty",
                label="Plan availability",
                value=plan.calendar_status,
                reason=plan.explanation,
            )
        )

    scenario = _scenario_result(simulation)

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

    evidence = [
        "readiness.score",
        "readiness.confidence",
        "harness.forecast.0.value",
        "harness.policy_decisions.0.value",
    ]
    if plan and plan.proposals:
        evidence.append("harness.plan.0.value")
    if scenario:
        evidence.append("harness.scenarios.0.explanation")

    return FitnessHarnessResult(
        issued_at=utcnow(),
        state=state_metrics,
        forecast=forecast_summary,
        policy_decisions=policy,
        plan=plan_checks[:8],
        scenarios=[scenario] if scenario else [],
        evidence=evidence,
        allowed_actions=[
            "explain_readiness",
            "explain_forecast",
            "explain_plan",
            "compare_scenario",
            "request_calendar_event_review",
        ],
        next_actions=next_actions,
        confidence=round(sum(confidence_parts) / len(confidence_parts), 2),
    )
