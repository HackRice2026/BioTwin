import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient

from core.api import create_app
from core.config import Settings
from narration.briefing import curate_briefing, CAPABILITIES
from narration.service import guard, resolve_evidence
from shared.schemas import utcnow


FACTS = ("Your estimated readiness is 62, in the balanced range relative to your pattern.",)


@pytest.mark.asyncio
async def test_curate_briefing_rejects_a_number_not_present_in_the_source_facts():
    def mock(request):
        return httpx.Response(
            200,
            json={"choices": [{"finish_reason": "stop", "message": {"content": "Readiness is 99 today."}}]},
        )

    config = Settings(_env_file=None, allow_external_narration=True, narration_api_key="k")
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        assert await curate_briefing(FACTS, config, client) is None


@pytest.mark.asyncio
async def test_curate_briefing_accepts_a_paraphrase_using_only_given_numbers():
    def mock(request):
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"finish_reason": "stop", "message": {"content": "Readiness sits at 62, a balanced day."}}
                ]
            },
        )

    config = Settings(_env_file=None, allow_external_narration=True, narration_api_key="k")
    async with httpx.AsyncClient(transport=httpx.MockTransport(mock)) as client:
        result = await curate_briefing(FACTS, config, client)
    assert result == "Readiness sits at 62, a balanced day."


@pytest.mark.asyncio
async def test_curate_briefing_unavailable_without_narration_configured():
    config = Settings(_env_file=None, allow_external_narration=False)
    async with httpx.AsyncClient() as client:
        assert await curate_briefing(FACTS, config, client) is None


def test_briefing_can_never_be_cited_as_evidence():
    from pathlib import Path
    from modeling.explanations import narration_context
    from shared.schemas import TwinState

    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    ctx = narration_context(state).model_copy(update={"briefing": "Some briefing text."})
    with pytest.raises(ValueError):
        resolve_evidence(ctx, "briefing")


def test_guard_ignores_briefing_when_checking_an_empty_evidence_answer():
    from modeling.explanations import narration_context
    from pathlib import Path
    from shared.schemas import TwinState

    state = TwinState.model_validate_json(Path("fixtures/golden/twin-state.json").read_text())
    ctx = narration_context(state).model_copy(update={"briefing": CAPABILITIES + " Some made-up 4242 number."})
    # A number that only exists in the briefing, never in facts, must still be rejected.
    assert not guard("Your score is 4242.", ctx)


@pytest.fixture
def briefing_client(tmp_path):
    config = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/briefing.db",
        demo_enabled=False,
        narration_api_key="gemini-test",
        allow_external_narration=True,
    )
    calls = []

    def mock(request):
        calls.append(request)
        body = json.loads(request.content)
        if body.get("model") == config.insight_model:
            return httpx.Response(
                200,
                json={"choices": [{"finish_reason": "stop", "message": {"content": "Steady day, nothing urgent."}}]},
            )
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]})

    with TestClient(create_app(config)) as client:
        runtime = client.app.state.runtime
        client.portal.call(runtime.http.aclose)
        runtime.http = httpx.AsyncClient(transport=httpx.MockTransport(mock))
        client.provider_calls = calls
        client.portal_ref = client.portal
        yield client


def register(client, email="briefing@example.com"):
    response = client.post(
        "/auth/session/register", json={"email": email, "password": "briefing-test-password", "adult": True}
    )
    assert response.status_code == 200
    return response.json()["user"]["id"]


def test_turn_context_persists_and_reuses_a_curated_briefing(briefing_client):
    client = briefing_client
    uid = register(client)
    rt = client.app.state.runtime
    u = rt.store.user(uid)

    async def first_pass():
        await rt.turn_context(u)
        # The refresh is fire-and-forget; give it one loop turn to finish writing.
        for _ in range(50):
            if rt.store.get(uid, "agent_briefing"):
                break
            await asyncio.sleep(0.02)

    client.portal.call(first_pass)
    doc = rt.store.get(uid, "agent_briefing")
    assert doc and doc["narrative"] == "Steady day, nothing urgent."

    rt.invalidate_turn_context(uid)
    turn = client.portal.call(rt.turn_context, u)
    assert "Steady day, nothing urgent." in turn["ctx"].briefing
    assert CAPABILITIES in turn["ctx"].briefing


def test_stale_briefing_does_not_trigger_a_second_refresh_while_one_is_in_flight(briefing_client):
    client = briefing_client
    uid = register(client)
    rt = client.app.state.runtime
    u = rt.store.user(uid)
    rt.store.put(uid, "agent_briefing", {"narrative": "Old news.", "generated_at": utcnow().timestamp() - 10_000})

    async def two_calls():
        await rt.turn_context(u)
        rt.invalidate_turn_context(u["id"])
        await rt.turn_context(u)

    client.portal.call(two_calls)
    assert sum(json.loads(r.content).get("model") == rt.config.insight_model for r in client.provider_calls) <= 1
