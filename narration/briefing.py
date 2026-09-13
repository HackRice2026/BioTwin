"""Turns one account's raw grounding facts into a short briefing a fast, non-technical
voice model can read directly instead of re-organizing raw facts on every turn.

The briefing is written by a stronger model (config.insight_model) but is NEVER itself a
source of truth: narration/service.py's resolve_evidence() refuses to resolve "briefing"
as an evidence path, so every number the coach actually speaks still has to trace back to
NarrationContext.facts/coach_brief/plan directly, exactly as before this existed. This
only saves the fast model the work of organizing what it already had.
"""

import asyncio
import re

import httpx

from narration.vertex_auth import vertex_token

NUMBERS = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")

# Hand-maintained, not data-driven, so it is never sent through the curation model --
# refreshed by a person when a feature actually changes, not on a timer.
CAPABILITIES = """How BioTwin's own features work, for explaining them when asked:
Best Training Window scores every free time slot between waking and three hours before
bedtime using projected Body Battery, time-of-day preference, forecast confidence, and
free time, then picks the highest score; it skips anything within 10 minutes of a
calendar entry. Simulate My Day layers deterministic what-if adjustments (train now,
train at the best window, extra steps, a short recovery break) on top of that same
forecast, so those are planning estimates, not a second physiological model. The Body
Battery forecast itself comes from a ridge model fitted in MATLAB for the first hour,
and this person's own hour-of-day rhythm beyond that, whichever measures better at each
horizon. Readiness is a separate 0-100 recovery estimate from sleep, HRV and resting
heart rate, not Garmin's Body Battery."""


def _validated(text, allowed_numbers):
    if not text or not text.strip() or len(text) > 1200:
        return False
    return all(n in allowed_numbers for n in NUMBERS.findall(text))


def _prompt(facts):
    return (
        "Rewrite the following facts about one person's current physiology, forecast, "
        "training plan, and any active what-if comparison into a short internal briefing "
        "(4-6 sentences) for a friendly, non-technical voice coach to read before answering "
        "questions. Organize it: current state, near-term forecast, best training window, "
        "any what-if comparison, then anything risky or worth flagging. Use ONLY the numbers "
        "already present in the facts, written as digits exactly as given -- never round, "
        "recompute, invent, or add a number, time, or claim not present below. This briefing "
        "will never be read aloud verbatim and is not itself evidence; it only orients the "
        "coach.\n\nFacts:\n" + "\n".join(f"- {fact}" for fact in facts)
    )


async def _curate_vertex(facts, config, http):
    try:
        token = await asyncio.to_thread(vertex_token)
    except Exception:
        return None
    url = (
        f"https://{config.vertex_region}-aiplatform.googleapis.com/v1/projects/"
        f"{config.vertex_project_id}/locations/{config.vertex_region}/publishers/google/"
        f"models/{config.vertex_insight_model}:generateContent"
    )
    try:
        response = await http.post(
            url,
            timeout=httpx.Timeout(30, connect=5),
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json={
                "contents": [{"role": "user", "parts": [{"text": _prompt(facts)}]}],
                "generationConfig": {
                    "temperature": 0,
                    # gemini-2.5-pro can't fully disable thinking (thinkingBudget: 0 is
                    # rejected -- only the flash tiers allow that), so this pins it to
                    # its minimum instead and leaves enough room after it for the
                    # briefing itself; without either, the whole token budget went to
                    # thinking and the response hit MAX_TOKENS before writing anything.
                    "maxOutputTokens": 2000,
                    "thinkingConfig": {"thinkingBudget": 128},
                },
            },
        )
        response.raise_for_status()
        candidate = response.json()["candidates"][0]
        if candidate.get("finishReason") != "STOP":
            return None
        return candidate["content"]["parts"][0]["text"].strip()
    except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError):
        return None


async def _curate_ai_studio(facts, config, http):
    try:
        response = await http.post(
            config.narration_url,
            timeout=httpx.Timeout(30, connect=5),
            headers={"Authorization": f"Bearer {config.narration_api_key}"},
            json={
                "model": config.insight_model,
                "messages": [{"role": "user", "content": _prompt(facts)}],
                "temperature": 0,
                "max_tokens": 1000,
                "reasoning_effort": "low",
            },
        )
        response.raise_for_status()
        choice = response.json()["choices"][0]
        if choice.get("finish_reason") != "stop":
            return None
        return choice["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return None


async def curate_briefing(facts, config, http):
    """Returns a short natural-language briefing over `facts` (a sequence of already-
    grounded strings, e.g. NarrationContext.facts), or None if curation is unavailable
    or the model's output can't be verified against the numbers it was given.

    Mirrors narrate()'s own Vertex-vs-AI-Studio split (narration/service.py) instead of
    only ever using the AI Studio key: a briefing refresh must not go dark just because
    the AI Studio key's prepay balance is the thing currently blocked, when Vertex --
    already configured as the live conversation's own fallback -- bills separately."""
    if not facts or not config.allow_external_narration:
        return None
    allowed = {n for fact in facts for n in NUMBERS.findall(fact)}
    if config.use_vertex_narration and config.vertex_project_id:
        text = await _curate_vertex(facts, config, http)
    elif config.narration_api_key:
        text = await _curate_ai_studio(facts, config, http)
    else:
        return None
    return text if _validated(text, allowed) else None
