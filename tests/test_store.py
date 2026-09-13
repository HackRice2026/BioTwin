import asyncio
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
import pytest
from core.store import (
    POSTGRES_CONNECT_ARGS,
    POSTGRES_SESSION_SETTINGS,
    Store,
    configure_postgres_connection,
    engine_options,
)
from core.config import Settings
from core.runtime import Runtime
from ingestion.normalizer import normalize
from shared.schemas import TwinFrame, Provenance, utcnow


def test_postgres_connections_have_bounded_waits_and_recycle():
    options = engine_options("postgresql+psycopg://user:password@example.test/database")
    assert options == {
        "connect_args": POSTGRES_CONNECT_ARGS,
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_timeout": 5,
    }

    statements = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            pass

        def execute(self, statement):
            statements.append(statement)

    class Connection:
        autocommit = False

        def cursor(self):
            return Cursor()

    connection = Connection()
    configure_postgres_connection(connection, None)
    assert statements == list(POSTGRES_SESSION_SETTINGS)
    assert connection.autocommit is False


async def test_outbox_poll_does_not_block_the_event_loop(tmp_path, monkeypatch):
    runtime = Runtime(
        Settings(
            _env_file=None,
            database_url=f"sqlite:///{tmp_path}/worker.db",
            demo_enabled=False,
        )
    )

    def slow_claim():
        time.sleep(0.2)
        return None

    monkeypatch.setattr(runtime.store, "claim", slow_claim)
    worker = asyncio.create_task(runtime.worker())
    started = time.perf_counter()
    try:
        await asyncio.sleep(0.01)
        assert time.perf_counter() - started < 0.1
    finally:
        worker.cancel()
        await asyncio.gather(worker, return_exceptions=True)
        await runtime.http.aclose()
        runtime.store.engine.dispose()


async def test_maintenance_store_work_does_not_block_the_event_loop(tmp_path, monkeypatch):
    runtime = Runtime(
        Settings(
            _env_file=None,
            database_url=f"sqlite:///{tmp_path}/maintenance.db",
            demo_enabled=False,
        )
    )

    async def no_refresh():
        pass

    def slow_store_call(*_args):
        time.sleep(0.2)
        return []

    monkeypatch.setattr(runtime.oauth, "refresh_due", no_refresh)
    monkeypatch.setattr(runtime.store, "docs", slow_store_call)
    monkeypatch.setattr(runtime.store, "purge", slow_store_call)
    maintenance = asyncio.create_task(runtime.maintenance())
    started = time.perf_counter()
    try:
        await asyncio.sleep(0.01)
        assert time.perf_counter() - started < 0.1
    finally:
        maintenance.cancel()
        await asyncio.gather(maintenance, return_exceptions=True)
        await runtime.http.aclose()
        runtime.store.engine.dispose()


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
