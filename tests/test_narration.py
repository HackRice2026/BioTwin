import json
from pathlib import Path

import httpx
import pytest

from core.config import Settings
from modeling.explanations import narration_context
from narration.service import guard, narrate, SYSTEM_PROMPT, template
from shared.schemas import TwinState


@pytest.fixture
def context():
    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    return narration_context(state)


@pytest.mark.asyncio
async def test_gemini_receives_complete_context_and_returns_plain_answer(context):
    answer = f"Your estimated readiness is {context.readiness.score}."

    def mock(request):
        assert str(request.url) == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        assert request.headers["authorization"] == "Bearer test-gemini-key"
        body = json.loads(request.content)
        supplied = json.loads(body["messages"][1]["content"])
        assert supplied == {"question": "What is my readiness?", "context": context.model_dump(mode="json")}
        assert body["model"] == "gemini-3.1-flash-lite"
        assert "tools" not in body
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps({"answer": answer, "evidence": ["readiness.score"]})
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        result = await narrate(
            "What is my readiness?",
            context,
            Settings(_env_file=None, allow_external_narration=True, narration_api_key="test-gemini-key"),
            client,
        )
    assert result.answer == answer
    assert result.mode == "language_service"
    assert result.notice is None


@pytest.mark.asyncio
async def test_recent_turns_travel_separately_from_grounding_context(context):
    """recent_conversation must never widen what guard() will accept -- it's there to
    resolve "what about earlier", not to smuggle in new evidence."""

    def mock(request):
        body = json.loads(request.content)
        supplied = json.loads(body["messages"][1]["content"])
        assert supplied["recent_conversation"] == [
            {"question": "When should I train?", "answer": "Around 5 PM looks best."}
        ]
        assert supplied["context"] == context.model_dump(mode="json")
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {
                            "content": json.dumps(
                                {"answer": f"Readiness is {context.readiness.score}.", "evidence": ["readiness.score"]}
                            )
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        result = await narrate(
            "What about tomorrow?",
            context,
            Settings(_env_file=None, allow_external_narration=True, narration_api_key="test-gemini-key"),
            client,
            recent_turns=(("When should I train?", "Around 5 PM looks best."),),
        )
    assert result.mode == "language_service"


def test_no_recent_turns_keeps_the_payload_shape_unchanged(context):
    from narration.service import _payload

    assert json.loads(_payload("hi", context, ())) == {"question": "hi", "context": context.model_dump(mode="json")}


def test_persona_reads_like_a_coaching_friend_not_a_metrics_dump():
    lowered = SYSTEM_PROMPT.lower()
    assert "friend" in lowered
    assert "not like an analyst" in lowered or "not an analyst" in lowered
    assert "recent_conversation" in SYSTEM_PROMPT
    assert "current context is what actually happened" in lowered or "current context" in lowered


def test_plan_time_claims_must_match_coach_evidence(context):
    context = context.model_copy(
        update={"coach_brief": {"recommendation": "Try light movement at 5:00 PM UTC."}}
    )

    assert guard(
        "Your best window is 5 PM.",
        context,
        ["coach_brief.recommendation"],
    )
    assert not guard(
        "Your best window is 6:30 PM.",
        context,
        ["coach_brief.recommendation"],
    )


def test_coach_brief_keeps_fallback_conversational(context):
    answer = template("How am I doing today?", context)

    assert context.coach_brief["recommendation"] in answer
    assert "standardized units" not in answer
    assert "harness output" not in answer.lower()


def test_coach_brief_does_not_turn_driver_names_into_day_labels(context):
    assert context.readiness.state.value.replace("_", " ") in context.coach_brief["headline"]
    assert "day" in context.coach_brief["headline"]
    assert "sleep day" not in context.coach_brief["headline"].lower()
    assert "hrv day" not in context.coach_brief["headline"].lower()
    assert any("HRV" in reason for reason in context.coach_brief["why"])


def test_coach_brief_why_list_is_allowed_as_curated_evidence(context):
    assert guard(
        "Readiness is 54.9, which looks like a balanced day for your pattern.",
        context,
        ["coach_brief.why"],
    )


@pytest.mark.parametrize(
    "answer,evidence",
    [
        ("Your readiness feels like a sleep day.", ["coach_brief.headline"]),
        ("Your readiness feels like a resting heart rate day.", ["coach_brief.headline"]),
        ("Your readiness is 9999.", ["readiness.score"]),
        ("Your readiness is ninety nine.", ["readiness.score"]),
        ("Your heart rate is 54.4.", ["facts.999"]),
        ("You have diabetes.", []),
        ("This will cure your fatigue.", []),
        ("Your readiness is 54.4.", ["readiness.user_id"]),
        ("Your readiness is 54.4.", []),
    ],
)
def test_grounding_rejects_unsupported_claims(context, answer, evidence):
    assert not guard(answer, context, evidence)


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["timeout", "http", "malformed", "invented", "truncated"])
async def test_provider_failures_return_explicit_grounded_fallback(context, failure):
    def mock(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("timeout", request=request)
        if failure == "http":
            return httpx.Response(429, json={"error": "private provider detail"})
        if failure == "malformed":
            return httpx.Response(200, json={"choices": []})
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "finish_reason": "length" if failure == "truncated" else "stop",
                        "message": {
                            "content": json.dumps(
                                {"answer": "Your readiness is 9999.", "evidence": ["readiness.score"]}
                            )
                        },
                    }
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        result = await narrate(
            "Why am I tired?",
            context,
            Settings(_env_file=None, allow_external_narration=True, narration_api_key="test-key"),
            client,
        )
    assert result.mode == "guard_fallback"
    assert result.notice
    assert "9999" not in result.answer
    assert "private provider detail" not in result.model_dump_json()


@pytest.mark.asyncio
async def test_narration_key_never_sent_to_configured_foreign_host(context):
    async def mock(request):
        raise AssertionError("No request should be sent")

    settings = Settings(
        _env_file=None,
        allow_external_narration=True,
        narration_api_key="secret",
        narration_url="https://untrusted.example/chat/completions",
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        result = await narrate("How am I doing?", context, settings, client)
    assert result.mode == "guard_fallback"
    assert "configuration" in result.notice
