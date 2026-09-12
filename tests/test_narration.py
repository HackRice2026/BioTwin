import json
from pathlib import Path

import httpx
import pytest

from core.config import Settings
from modeling.explanations import narration_context
from narration.service import guard, narrate
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


@pytest.mark.parametrize(
    "answer,evidence",
    [
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
