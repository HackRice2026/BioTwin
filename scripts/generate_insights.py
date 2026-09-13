"""Turn the locked MATLAB model-comparison results (matlab/results/BASELINES.md,
docs/Matlab.md) into short, embedded facts the voice coach can cite.

That analysis already ran once, offline, in MATLAB -- it is not something the live
request path should ever recompute, and today nothing in NarrationContext carries it at
all, so a question like "how accurate is your 1-hour forecast" has zero grounding. This
script asks a stronger Gemini model (INSIGHT_MODEL, not the fast/cheap one used for live
narration) to phrase each locked finding as one grounded paragraph, embeds it, and stores
it in analysis_insights via core.store.Store.put_insight so narration/insights.py can
retrieve it by similarity at ask time.

Every generated paragraph is checked the same way narration/service.py's guard() checks a
live answer: every digit string in the text must already appear in that finding's own
source numbers. A paragraph that fails falls back to a hand-written sentence using the
same numbers, so a missing/misconfigured INSIGHT_MODEL never leaves a topic unfilled with
something ungrounded instead.

    uv run python -m scripts.generate_insights
"""

import asyncio
import re

import httpx

from core.config import Settings
from core.store import Store
from narration.embeddings import embed_text

NUMBERS = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?")

# Numbers locked in matlab/results/BASELINES.md; see "## Validation results" and
# "# Stage 3, run in MATLAB: the trees change the answer" there for how they were produced.
FINDINGS = [
    {
        "topic": "forecast_accuracy_1h",
        "numbers": ["1", "2.35", "1.99", "1.92"],
        "source": (
            "At the 1 hour Body Battery forecast horizon, the strongest simple rule "
            "(recent-trend extrapolation) reaches 2.35 mean absolute error. A ridge "
            "regression model using the same physiology predictors reaches 1.99. A "
            "boosted regression trees model (LSBoost) reaches 1.92, the best result "
            "at this horizon."
        ),
        "fallback": (
            "At the 1-hour forecast horizon, trend extrapolation alone reaches 2.35 mean "
            "absolute error. Boosted regression trees (LSBoost) do better, at 1.92 -- the "
            "best result MATLAB found at this horizon."
        ),
    },
    {
        "topic": "forecast_accuracy_3h",
        "numbers": ["3", "5.20", "6.32", "4.84", "5.35"],
        "source": (
            "At the 3 hour Body Battery forecast horizon, the strongest simple rule "
            "(trend plus time-of-day) reaches 5.20 mean absolute error. A ridge "
            "regression model reaches only 6.32, worse than the rule. A bagged "
            "regression trees model reaches 4.84, the best result at this horizon. "
            "A boosted trees model reaches 5.35."
        ),
        "fallback": (
            "At the 3-hour horizon, the best simple rule reaches 5.20 mean absolute "
            "error. A linear ridge model actually loses to it at 6.32, but bagged "
            "regression trees reach 4.84 -- the information was there, the linear form "
            "just couldn't use it."
        ),
    },
    {
        "topic": "forecast_accuracy_6h",
        "numbers": ["6", "7.37", "8.47", "8.91", "11.16"],
        "source": (
            "At the 6 hour Body Battery forecast horizon, a simple time-of-day rule "
            "(the train-set average for that hour, ignoring the current state) reaches "
            "7.37 mean absolute error and beats every machine-learning model tested: "
            "bagged trees reach 8.47, boosted trees reach 8.91, and a Gaussian process "
            "reaches 11.16."
        ),
        "fallback": (
            "At the 6-hour horizon, nothing beat a plain time-of-day rule at 7.37 mean "
            "absolute error -- not bagged trees (8.47), not boosted trees (8.91), not a "
            "Gaussian process (11.16). That's the honest limit of the current models."
        ),
    },
]


def _validated(text, allowed_numbers):
    if not text or not text.strip() or len(text) > 600:
        return False
    return all(n in allowed_numbers for n in NUMBERS.findall(text))


async def _write_finding(finding, config, http):
    if not config.allow_external_narration or not config.narration_api_key:
        return finding["fallback"]
    prompt = (
        "Rewrite the following locked model-evaluation finding as one short, plain-English "
        "paragraph (2-3 sentences) for a fitness coach voice assistant to say aloud. "
        "Use ONLY the numbers already present in the finding, written as digits, exactly as "
        "given -- do not round, convert, recompute, or spell any number out as a word. Do not "
        "add any number, date, or claim not present in the finding.\n\nFinding: "
        f"{finding['source']}"
    )
    try:
        response = await http.post(
            config.narration_url,
            timeout=httpx.Timeout(30, connect=5),
            headers={"Authorization": f"Bearer {config.narration_api_key}"},
            json={
                "model": config.insight_model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0,
                "max_tokens": 300,
            },
        )
        response.raise_for_status()
        text = response.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError):
        return finding["fallback"]
    return text if _validated(text, set(finding["numbers"])) else finding["fallback"]


async def main():
    config = Settings()
    store = Store(config.database_url)
    async with httpx.AsyncClient(timeout=30) as http:
        for finding in FINDINGS:
            content = await _write_finding(finding, config, http)
            embedding = await embed_text(content, config, http)
            if not embedding:
                print(f"skipped {finding['topic']}: embeddings unavailable (check NARRATION_API_KEY)")
                continue
            store.put_insight(finding["topic"], content, finding["numbers"], embedding)
            print(f"stored {finding['topic']}: {content}")


if __name__ == "__main__":
    asyncio.run(main())
