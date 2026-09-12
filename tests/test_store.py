import os
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from core.store import Store
from ingestion.normalizer import normalize
from shared.schemas import TwinFrame, Provenance, utcnow


@pytest.fixture(params=["sqlite", "postgres"])
def store(request, tmp_path):
    url = f"sqlite:///{tmp_path}/store.db"
    if request.param == "postgres":
        url = os.getenv("TEST_POSTGRES_URL")
        if not url:
            pytest.skip("TEST_POSTGRES_URL is not configured")
    instance = Store(url)
    yield instance
    instance.engine.dispose()


def test_concurrent_duplicate_commits_and_prediction_immutability(store):
    uid = uuid.uuid4().hex
    store.create_user(uid, uid + "@test.invalid", "unused", "Test", {})
    f = normalize(
        TwinFrame(user_id=uid, event_time=utcnow(), heart_rate_bpm=70, provenance=Provenance.GARMIN_LIVE)
    )
    try:
        with ThreadPoolExecutor(max_workers=8) as pool:
            results = list(pool.map(lambda _: store.append(f), range(12)))
        assert sum(r is not None for r in results) == 1
        assert len(store.history(uid)) == 1
        assert store.user(uid)["sequence"] == 1
        store.put(uid, "prediction", {"curve": [70, 65]}, "p", immutable=True)
        with pytest.raises(ValueError, match="cannot be overwritten"):
            store.put(uid, "prediction", {"curve": [70, 60]}, "p", immutable=True)
        assert store.get(uid, "prediction", "p") == {"curve": [70, 65]}
    finally:
        store.delete_user(uid)


def test_user_deletion_scrubs_only_their_webhook_batch(store):
    uid = uuid.uuid4().hex
    store.create_user(uid, uid + "@test.invalid", "unused", "Test", {})
    store.put(uid, "identity", {"vendor_id": "vendor-" + uid, "user_id": uid, "provider": "garmin"}, "garmin")
    store.enqueue(
        "garmin",
        {"dailies": [{"userId": "vendor-" + uid, "steps": 500}, {"userId": "another-user", "steps": 600}]},
    )
    store.delete_user(uid)
    job = store.claim()
    assert job["payload"] == {"dailies": [{"userId": "another-user", "steps": 600}]}
    store.finish(job)


def test_conversation_persistence_idempotence_and_deletion(store):
    from shared.schemas import NarrationResponse

    uid = uuid.uuid4().hex
    cid = uuid.uuid4().hex
    store.create_user(uid, uid + "@test.invalid", "unused", "Transcript test", {})
    try:
        row, created = store.begin_conversation(
            uid, cid, "How am I doing?", {"facts": ["Recorded test context"]}
        )
        assert created and row["mode"] == "pending"
        _, duplicate = store.begin_conversation(uid, cid, "How am I doing?", {"facts": []})
        assert not duplicate
        saved = store.complete_conversation(
            uid,
            cid,
            NarrationResponse(
                answer="The requested measurement is unavailable.",
                mode="language_service",
                model="test-model",
            ),
        )
        assert saved["gemini_answer"] == saved["answer"]
        assert saved["completed_at"] >= saved["created_at"]
        reopened = Store(store.engine.url.render_as_string(hide_password=False))
        try:
            assert reopened.conversation_history(uid)[0]["answer"] == saved["answer"]
        finally:
            reopened.engine.dispose()
        store.delete_user(uid)
        assert store.conversation_history(uid) == []
        assert (
            store.complete_conversation(uid, cid, NarrationResponse(answer="Late answer", mode="template"))
            is None
        )
    finally:
        store.delete_user(uid)
