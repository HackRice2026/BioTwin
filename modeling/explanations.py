from shared.schemas import NarrationContext
from modeling.harness import build_harness
from zoneinfo import ZoneInfo


def narration_context(state, plan=None, readiness_history=(), outlook=None):
    r, b = state.readiness, state.baseline_summary
    facts = []
    if state.energy_reserve_pct is not None:
        facts.append(
            f"Your BioTwin Body Battery estimate is {state.energy_reserve_pct} percent. "
            "It combines readiness signals with available heart-rate recovery; it is not Garmin's Body Battery or a medical measure."
        )
    if r.score is not None:
        facts.append(
            f"Your estimated readiness is {r.score:g}, in the {r.state.value.replace('_', ' ')} range relative to your pattern."
        )
    else:
        facts.append("I need recent wearable measurements before I can estimate your readiness.")
    for signal, value in sorted(r.contributions.items(), key=lambda x: x[1]):
        facts.append(
            f"The {signal.replace('_', ' ')} contribution to your score is {value:g} standardized units."
        )
    if r.degraded_reason:
        facts.append(f"Some signals are missing: {r.degraded_reason.lower()}. Confidence is reduced.")
    facts.append(
        f"Personal calibration is {round(b.shrinkage_weight * 100)} percent. The remaining baseline weight uses engineering priors."
    )
    if b.recovery_tau_s:
        facts.append(
            f"Your fitted heart-rate recovery time constant is {b.recovery_tau_s:g} seconds, across {b.tau_fit_n_sessions} sessions."
        )
        facts.append(
            f"Held-out recovery error averages {b.tau_fit_rmse:g} beats per minute. It describes model error, not a guaranteed outcome."
        )
    else:
        facts.append("There are not enough usable recovery sessions to fit your personal recovery time yet.")
    if state.latest:
        for field, label, unit in [
            ("heart_rate_bpm", "heart rate", "beats per minute"),
            ("hrv_rmssd_ms", "HRV RMSSD", "milliseconds"),
            ("resting_hr_bpm", "resting heart rate", "beats per minute"),
            ("respiration_brpm", "respiration", "breaths per minute"),
            ("spo2_pct", "oxygen saturation", "percent"),
            ("steps", "step count", "steps"),
            ("active_kcal", "active calories burned", "kilocalories"),
        ]:
            value = getattr(state.latest, field)
            if value is not None:
                facts.append(f"Your latest recorded {label} is {value:g} {unit}.")
        if state.latest.sleep:
            facts.append(f"Your latest recorded sleep lasted {state.latest.sleep.total_minutes} minutes.")
    if plan:
        facts.append(plan.explanation)
        for p in plan.proposals:
            local_start = p.start.astimezone(ZoneInfo(plan.timezone))
            facts.append(
                f"Your plan suggests {p.title.lower()} at {local_start.strftime('%H:%M %Z')}. {p.reason}"
            )
    harness = build_harness(state, plan, outlook)
    facts.append(
        f"My coaching confidence for this recommendation is {harness.confidence:g}, based on signal confidence, forecast confidence, and calendar availability."
    )
    for decision in harness.policy_decisions[:2]:
        facts.append(f"Coaching guardrail: {decision.label} is {decision.value}. {decision.reason}")
    for action in harness.next_actions[:2]:
        facts.append(f"Recommended next step: {action}")
    trend = []
    scores = [
        x for x in sorted(readiness_history, key=lambda x: x["computed_at"]) if x.get("score") is not None
    ]
    if len(scores) >= 2:
        delta = round(scores[-1]["score"] - scores[0]["score"], 1)
        trend.append(
            f"Across the available recorded days, your estimated readiness changed by {delta:g} points. This describes a score trend, not a cause in your body."
        )
        facts.extend(trend)
    return NarrationContext(
        readiness=r,
        baseline_summary=b,
        plan=plan,
        prediction=state.prediction,
        harness=harness,
        facts=tuple(facts),
        recent_trend=tuple(trend),
        provenance=state.provenance_banner,
        quality=state.quality,
    )
