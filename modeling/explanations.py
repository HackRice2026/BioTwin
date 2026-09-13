from shared.schemas import NarrationContext
from zoneinfo import ZoneInfo


SIGNAL_LABELS = {
    "hrv": "HRV",
    "hrv_rmssd": "HRV",
    "resting_hr": "resting heart rate",
    "sleep_debt": "sleep debt",
}


def _signal_label(signal):
    return SIGNAL_LABELS.get(signal, signal.replace("_", " "))


def _coach_time(stamp):
    return stamp.strftime("%I:%M %p %Z").lstrip("0")


def _coach_brief(state, plan, trajectory=None):
    readiness = state.readiness
    label = readiness.state.value.replace("_", " ")
    score = f"{readiness.score:g}" if readiness.score is not None else "unknown"
    recommendation = "Keep the next step simple and let the plan pick the cleanest window."
    if plan and plan.proposals:
        p = plan.proposals[0]
        local_start = p.start.astimezone(ZoneInfo(plan.timezone))
        duration = int((p.end - p.start).total_seconds() / 60)
        recommendation = (
            f"I'd use the {_coach_time(local_start)} opening for "
            f"a {duration}-minute {p.title.lower()}."
        )
    elif trajectory and trajectory.get("available") and trajectory.get("points"):
        recommendation = "Time your effort around where your energy is headed."
    strongest = sorted(readiness.contributions.items(), key=lambda x: abs(x[1]), reverse=True)[:2]
    why = []
    if readiness.score is not None:
        why.append(f"Readiness is {score}, which looks like a {label} day for your pattern.")
    for signal, value in strongest:
        direction = "helping the score" if value > 0 else "pulling the score down"
        signal_label = _signal_label(signal)
        why.append(f"{signal_label[:1].upper()}{signal_label[1:]} is {direction} right now.")
    if plan and plan.proposals:
        p = plan.proposals[0]
        local_start = p.start.astimezone(ZoneInfo(plan.timezone))
        why.append(f"The cleanest plan option is {p.title.lower()} at {_coach_time(local_start)}.")
    if trajectory and trajectory.get("available") and trajectory.get("points"):
        first = trajectory["points"][0]
        why.append(
            f"Energy is {trajectory['current']:g} now and projects to {first['value']:g} in {first['horizon_minutes']} minutes."
        )
    return {
        "role": "friendly data-backed fitness coach",
        "voice": (
            "casual, concise, warm, and useful; avoid dashboard language, field names, "
            "medical claims, and long metric lists"
        ),
        "headline": f"Readiness is {score} and feels like a {label} day.",
        "recommendation": recommendation,
        "why": why[:4],
        "confidence": f"Readiness confidence is {readiness.confidence:g}.",
    }


def narration_context(state, plan=None, readiness_history=(), outlook=None, trajectory=None):
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
    if trajectory:
        if trajectory.get("available"):
            facts.append(
                f"Body Battery trajectory basis is {trajectory['basis']}; current value is {trajectory['current']:g}, measured {trajectory['measured_age_minutes']:g} minutes ago."
            )
            for point in trajectory.get("points", [])[:3]:
                facts.append(
                    f"Body Battery forecast at {point['horizon_minutes']} minutes is {point['value']:g}, with validation MAE {point['validation_mae']:g}; method {point['method']}."
                )
            if trajectory.get("reason"):
                facts.append(trajectory["reason"])
        else:
            facts.append(trajectory.get("reason", "Body Battery trajectory is unavailable."))
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
        coach_brief=_coach_brief(state, plan, trajectory),
        readiness=r,
        baseline_summary=b,
        plan=plan,
        prediction=state.prediction,
        facts=tuple(facts),
        recent_trend=tuple(trend),
        provenance=state.provenance_banner,
        quality=state.quality,
    )
