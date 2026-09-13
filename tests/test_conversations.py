import json
from datetime import timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from core.api import create_app
from core.config import Settings
from core.store import Store, conversations
from shared.schemas import utcnow


def register(client, email="voice@example.com"):
    response = client.post(
        "/auth/session/register", json={"email": email, "password": "voice-test-password", "adult": True}
    )
    assert response.status_code == 200
    return response.json()["user"]["id"]


@pytest.fixture
def client(tmp_path):
    config = Settings(
        _env_file=None,
        database_url=f"sqlite:///{tmp_path}/conversations.db",
        demo_enabled=False,
        narration_api_key="gemini-test",
        allow_external_narration=True,
        elevenlabs_api_key="eleven-test",
    )
    calls = []

    def mock(request):
        calls.append(request)
        if request.url.host == "generativelanguage.googleapis.com":
            data = json.loads(json.loads(request.content)["messages"][1]["content"])
            facts = data["context"]["facts"]
            index = next((i for i, fact in enumerate(facts) if "latest recorded heart rate" in fact), None)
            result = {
                "answer": facts[index]
                if index is not None
                else "That measurement is not in my current context.",
                "evidence": [f"facts.{index}"] if index is not None else [],
            }
            return httpx.Response(
                200, json={"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}
            )
        return httpx.Response(200, content=b"ID3-audio", headers={"Content-Type": "audio/mpeg"})

    with TestClient(create_app(config)) as client:
        runtime = client.app.state.runtime
        client.portal.call(runtime.http.aclose)
        runtime.http = httpx.AsyncClient(transport=httpx.MockTransport(mock))
        client.provider_calls = calls
        yield client


def test_exchange_persists_gemini_answer_and_speech_uses_same_text(client):
    uid = register(client)
    client.post("/api/ingest/bluetooth", json={"heart_rate_bpm": 76})
    reply = client.post(
        "/api/twin/ask", json={"question": "What is my heart rate?", "request_id": "same-request-000001"}
    ).json()
    assert reply["mode"] == "language_service"
    assert "76" in reply["answer"]
    assert client.get("/api/voice/" + reply["reply_id"]).content == b"ID3-audio"
    assert json.loads(client.provider_calls[-1].content)["text"] == reply["answer"]
    assert client.provider_calls[-1].headers["xi-api-key"] == "eleven-test"
    history = client.get("/api/twin/conversations").json()["conversations"]
    assert history[0]["answer"] == reply["answer"]
    assert history[0]["created_at"] and history[0]["completed_at"]
    store = Store(client.app.state.runtime.config.database_url)
    try:
        row = store.conversation(uid, reply["id"])
        assert row["gemini_answer"] == reply["answer"]
        assert row["context"]["readiness"]["user_id"] == uid
    finally:
        store.engine.dispose()
    replay = client.post(
        "/api/twin/ask", json={"question": "What is my heart rate?", "request_id": "same-request-000001"}
    )
    assert replay.json()["id"] == reply["id"]
    assert sum(r.url.host == "generativelanguage.googleapis.com" for r in client.provider_calls) == 1
    assert len(client.get("/api/twin/conversations").json()["conversations"]) == 1
    assert (
        client.post(
            "/api/twin/ask", json={"question": "Different question", "request_id": "same-request-000001"}
        ).status_code
        == 422
    )


def test_transcripts_and_replay_are_account_scoped_and_deleted(client):
    uid = register(client)
    reply = client.post("/api/twin/ask", json={"question": "How am I?"}).json()
    assert client.get("/api/data/export").json()["conversations"][0]["id"] == reply["id"]
    client.post("/auth/session/logout")
    register(client, "other@example.com")
    assert client.get("/api/twin/conversations?user_id=" + uid).json()["conversations"] == []
    assert client.get("/api/voice/" + reply["reply_id"]).status_code == 404
    assert client.post(f"/api/twin/conversations/{reply['id']}/speech").status_code == 404
    client.post("/auth/session/logout")
    client.post("/auth/session/login", json={"email": "voice@example.com", "password": "voice-test-password"})
    ticket = client.post(f"/api/twin/conversations/{reply['id']}/speech").json()
    assert client.get("/api/voice/" + ticket["reply_id"]).status_code == 200
    client.delete("/api/data")
    assert client.app.state.runtime.store.conversation_history(uid) == []


@pytest.mark.parametrize("failure", ["http", "timeout", "empty"])
def test_voice_failure_preserves_saved_text(client, failure):
    register(client)
    reply = client.post("/api/twin/ask", json={"question": "How am I?"}).json()

    def mock(request):
        if failure == "timeout":
            raise httpx.ReadTimeout("unavailable", request=request)
        return httpx.Response(503 if failure == "http" else 200, content=b"")

    runtime = client.app.state.runtime
    client.portal.call(runtime.http.aclose)
    runtime.http = httpx.AsyncClient(transport=httpx.MockTransport(mock))
    response = client.get("/api/voice/" + reply["reply_id"])
    assert response.status_code == 502
    assert "ElevenLabs" in response.json()["detail"]
    assert client.get("/api/twin/conversations").json()["conversations"][0]["answer"] == reply["answer"]


def test_failed_gemini_exchange_is_saved_with_explicit_fallback(client):
    register(client)
    runtime = client.app.state.runtime
    client.portal.call(runtime.http.aclose)
    runtime.http = httpx.AsyncClient(transport=httpx.MockTransport(lambda _: httpx.Response(503)))
    reply = client.post("/api/twin/ask", json={"question": "Why am I tired?"}).json()
    assert reply["mode"] == "guard_fallback"
    assert reply["notice"]
    assert client.get("/api/twin/conversations").json()["conversations"][0]["answer"] == reply["answer"]


def test_guest_transcripts_are_private_to_each_browser(tmp_path):
    settings = Settings(_env_file=None, database_url=f"sqlite:///{tmp_path}/demo.db")
    with TestClient(create_app(settings)) as client:
        reply = client.post("/api/twin/ask", json={"question": "How am I doing?"}).json()
        assert client.get("/api/twin/conversations").json()["conversations"][0]["id"] == reply["id"]
        client.cookies.clear()
        assert client.get("/api/twin/conversations").json()["conversations"] == []
        assert client.post(f"/api/twin/conversations/{reply['id']}/speech").status_code == 404


def test_history_pagination_and_retention(client):
    uid = register(client)
    ids = [client.post("/api/twin/ask", json={"question": f"Question {n}?"}).json()["id"] for n in range(3)]
    page = client.get("/api/twin/conversations?limit=2").json()
    assert [row["id"] for row in page["conversations"]] == ids[1:]
    older = client.get("/api/twin/conversations?before=" + page["next_before"]).json()
    assert [row["id"] for row in older["conversations"]] == ids[:1]
    store = client.app.state.runtime.store
    with store.engine.begin() as db:
        db.execute(
            conversations.update()
            .where(conversations.c.id == ids[0])
            .values(created_at=(utcnow() - timedelta(days=100)).timestamp())
        )
    store.purge(90)
    assert [row["id"] for row in store.conversation_history(uid)] == ids[1:]
    with store.engine.connect() as db:
        assert db.execute(select(conversations.c.id).where(conversations.c.id == ids[0])).first() is None


def test_timestamped_speech_is_scoped_and_preserves_alignment(client):
    register(client)
    reply = client.post("/api/twin/ask", json={"question": "How am I?"}).json()
    chunk = {"audio_base64": "SUQz", "alignment": {"characters": ["H", "i"],
             "character_start_times_seconds": [0, .1], "character_end_times_seconds": [.1, .2]}}
    calls = []

    def timed(request):
        calls.append(request)
        return httpx.Response(200, content=json.dumps(chunk) + "\n")

    runtime = client.app.state.runtime
    client.portal.call(runtime.http.aclose)
    runtime.http = httpx.AsyncClient(transport=httpx.MockTransport(timed))
    response = client.get(f"/api/voice/{reply['reply_id']}?timestamps=true")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert response.headers["cache-control"] == "no-store"
    assert response.json() == chunk
    assert calls[0].url.path.endswith("/stream/with-timestamps")
    assert json.loads(calls[0].content)["text"] == reply["answer"]
    assert client.get(f"/api/voice/{reply['reply_id']}?timestamps=true").status_code == 404
