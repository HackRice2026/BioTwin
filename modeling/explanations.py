from shared.schemas import NarrationContext


def narration_context(state, plan=None, readiness_history=()):
    r, b = state.readiness, state.baseline_summary
    facts = []
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
        ]:
            value = getattr(state.latest, field)
            if value is not None:
                facts.append(f"Your latest recorded {label} is {value:g} {unit}.")
        if state.latest.sleep:
            facts.append(f"Your latest recorded sleep lasted {state.latest.sleep.total_minutes} minutes.")
    if plan:
        facts.append(plan.explanation)
        for p in plan.proposals:
            facts.append(f"Your plan suggests {p.title.lower()} at {p.start.strftime('%H:%M')}. {p.reason}")
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
        facts=tuple(facts),
        recent_trend=tuple(trend),
    )
