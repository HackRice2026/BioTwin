"""Portable transactional persistence. Raw frames are append-only; derived documents are replaceable."""

import hashlib
import secrets
import time
from datetime import timedelta, datetime
from pathlib import Path
from threading import RLock
from sqlalchemy import (
    create_engine,
    MetaData,
    Table,
    Column,
    String,
    Integer,
    Float,
    JSON,
    Text,
    UniqueConstraint,
    select,
    insert,
    update,
    delete,
    func,
    event,
)
from sqlalchemy.exc import IntegrityError
from shared.schemas import TwinFrame, utcnow

metadata = MetaData()
users = Table(
    "users",
    metadata,
    Column("id", String, primary_key=True),
    Column("email", String, unique=True),
    Column("password", String),
    Column("name", String),
    Column("profile", JSON),
    Column("sequence", Integer, default=0, nullable=False),
)
frames = Table(
    "measurements",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("user_id", String, index=True),
    Column("event_time", Float, index=True),
    Column("ingest_time", Float),
    Column("provenance", String),
    Column("dedupe_key", String),
    Column("sequence", Integer),
    Column("payload", JSON),
    UniqueConstraint("user_id", "dedupe_key"),
)
documents = Table(
    "documents",
    metadata,
    Column("user_id", String, primary_key=True),
    Column("kind", String, primary_key=True),
    Column("key", String, primary_key=True),
    Column("payload", JSON),
)
sessions = Table(
    "sessions",
    metadata,
    Column("hash", String, primary_key=True),
    Column("user_id", String),
    Column("expires", Float),
)
conversations = Table(
    "conversations",
    metadata,
    Column("id", String, primary_key=True),
    Column("user_id", String, nullable=False, index=True),
    Column("question", Text, nullable=False),
    Column("answer", Text),
    Column("gemini_answer", Text),
    Column("created_at", Float, nullable=False, index=True),
    Column("completed_at", Float),
    Column("mode", String, nullable=False),
    Column("notice", Text),
    Column("model", String),
    Column("context", JSON, nullable=False),
)
outbox = Table(
    "outbox",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("provider", String),
    Column("payload", JSON),
    Column("status", String),
    Column("attempts", Integer),
    Column("available", Float),
    Column("error", Text),
)


POSTGRES_CONNECT_ARGS = {
    "connect_timeout": 5,
    "keepalives": 1,
    "keepalives_idle": 30,
    "keepalives_interval": 10,
    "keepalives_count": 3,
    "tcp_user_timeout": 5000,
}
POSTGRES_SESSION_SETTINGS = (
    "SET statement_timeout = 10000",
    "SET lock_timeout = 5000",
    "SET idle_in_transaction_session_timeout = 10000",
)


def engine_options(url):
    options = {"pool_pre_ping": True}
    if url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
    elif url.startswith("postgresql"):
        options.update(
            connect_args=POSTGRES_CONNECT_ARGS,
            pool_recycle=300,
            pool_timeout=5,
        )
    return options


def configure_postgres_connection(dbapi, _connection_record):
    """Bound every server-side wait on each newly opened pooled session."""
    previous_autocommit = dbapi.autocommit
    try:
        dbapi.autocommit = True
        with dbapi.cursor() as cursor:
            for statement in POSTGRES_SESSION_SETTINGS:
                cursor.execute(statement)
    finally:
        dbapi.autocommit = previous_autocommit


class Store:
    def __init__(self, url: str):
        if url.startswith("sqlite:///./"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, **engine_options(url))
        if url.startswith("sqlite"):

            @event.listens_for(self.engine, "connect")
            def configure(dbapi, _):
                dbapi.execute("PRAGMA journal_mode=WAL")
                dbapi.execute("PRAGMA busy_timeout=10000")
        elif url.startswith("postgresql"):
            event.listen(self.engine, "connect", configure_postgres_connection)

        self.lock = RLock()
        # Every request calls session_user() to authenticate, so on a networked
        # (Supabase/Postgres) database this was one blocking round-trip per
        # request minimum -- a single voice turn fires several requests (ask,
        # speech ticket, audio stream, history poll) back to back, and each one
        # froze the whole event loop waiting on the network. A session token is
        # immutable once issued, so a few seconds of staleness costs nothing;
        # this cache turns a burst of requests into one DB hit.
        self._session_cache: dict[str, tuple[dict | None, float]] = {}
        self._session_cache_ttl = 4.0
        metadata.create_all(self.engine)

    def user(self, user_id):
        with self.engine.connect() as c:
            row = c.execute(select(users).where(users.c.id == user_id)).mappings().first()
            return dict(row) if row else None

    def by_email(self, email):
        with self.engine.connect() as c:
            row = c.execute(select(users).where(users.c.email == email)).mappings().first()
            return dict(row) if row else None

    def create_user(self, user_id, email, password, name, profile):
        with self.engine.begin() as c:
            c.execute(
                insert(users).values(
                    id=user_id, email=email, password=password, name=name, profile=profile, sequence=0
                )
            )

    def ensure_guest(self, user_id):
        """Anonymous demo visitors write conversations/documents under a synthetic
        "guest:<hash>" owner id (see conversation_owner in api.py) so their questions
        stay private from other visitors sharing the public demo data. Every such
        write sits behind a real foreign key to `users` on Postgres though -- SQLite
        never enforced it, so this only surfaces once a Postgres-backed deployment is
        used: every guest write fails there without this placeholder row existing
        first. Idempotent; tolerates a concurrent request creating it first."""
        if self.user(user_id):
            return
        try:
            self.create_user(user_id, f"{user_id}@guest.invalid", "", "Guest", {})
        except IntegrityError:
            pass

    def save_profile(self, user_id, profile):
        with self.engine.begin() as c:
            c.execute(update(users).where(users.c.id == user_id).values(profile=profile))

    def create_session(self, user_id):
        token = secrets.token_urlsafe(48)
        with self.engine.begin() as c:
            c.execute(
                insert(sessions).values(
                    hash=hashlib.sha256(token.encode()).hexdigest(),
                    user_id=user_id,
                    expires=(utcnow() + timedelta(days=7)).timestamp(),
                )
            )
        return token

    def session_user(self, token):
        if not token:
            return None
        cached = self._session_cache.get(token)
        if cached and cached[1] > time.monotonic():
            return cached[0]
        with self.engine.connect() as c:
            row = c.execute(
                select(sessions.c.user_id).where(
                    sessions.c.hash == hashlib.sha256(token.encode()).hexdigest(),
                    sessions.c.expires > utcnow().timestamp(),
                )
            ).first()
        found = self.user(row[0]) if row else None
        self._session_cache[token] = (found, time.monotonic() + self._session_cache_ttl)
        return found

    def end_session(self, token):
        self._session_cache.pop(token, None)
        with self.engine.begin() as c:
            c.execute(delete(sessions).where(sessions.c.hash == hashlib.sha256(token.encode()).hexdigest()))

    def append(self, frame: TwinFrame) -> TwinFrame | None:
        with self.lock, self.engine.begin() as c:
            # A row lock serializes writers per user on Postgres; RLock covers SQLite in this process.
            seq = c.execute(
                select(users.c.sequence).where(users.c.id == frame.user_id).with_for_update()
            ).scalar_one()
            if c.execute(
                select(frames.c.id).where(
                    frames.c.user_id == frame.user_id, frames.c.dedupe_key == frame.dedupe_key
                )
            ).first():
                return None
            committed = frame.model_copy(update={"sequence": seq + 1})
            c.execute(
                insert(frames).values(
                    user_id=frame.user_id,
                    event_time=frame.event_time.timestamp(),
                    ingest_time=frame.ingest_time.timestamp(),
                    provenance=frame.provenance.value,
                    dedupe_key=frame.dedupe_key,
                    sequence=seq + 1,
                    payload=committed.model_dump(mode="json"),
                )
            )
            c.execute(update(users).where(users.c.id == frame.user_id).values(sequence=seq + 1))
        return committed

    def history(self, user_id, since=None, until=None, limit=None):
        q = select(frames.c.payload).where(frames.c.user_id == user_id)
        if since:
            q = q.where(frames.c.event_time >= since.timestamp())
        if until:
            q = q.where(frames.c.event_time <= until.timestamp())
        with self.engine.connect() as c:
            rows = (
                c.execute(q.order_by(frames.c.event_time.desc(), frames.c.sequence.desc()).limit(limit))
                .scalars()
                .all()
            )
        return [TwinFrame.model_validate(p) for p in reversed(rows)]

    def get(self, user_id, kind, key="current"):
        with self.engine.connect() as c:
            return c.execute(
                select(documents.c.payload).where(
                    documents.c.user_id == user_id, documents.c.kind == kind, documents.c.key == key
                )
            ).scalar_one_or_none()

    def put(self, user_id, kind, payload, key="current", immutable=False, require_user=False):
        with self.lock, self.engine.begin() as c:
            if (
                require_user
                and not c.execute(select(users.c.id).where(users.c.id == user_id).with_for_update()).first()
            ):
                raise ValueError("This account is no longer available")
            condition = (
                (documents.c.user_id == user_id) & (documents.c.kind == kind) & (documents.c.key == key)
            )
            exists = c.execute(select(documents.c.key).where(condition)).first()
            if exists:
                if immutable:
                    raise ValueError("Issued artifacts cannot be overwritten")
                c.execute(update(documents).where(condition).values(payload=payload))
            else:
                c.execute(insert(documents).values(user_id=user_id, kind=kind, key=key, payload=payload))

    def docs(self, user_id, kind):
        with self.engine.connect() as c:
            q = select(documents.c.key, documents.c.payload).where(documents.c.kind == kind)
            if user_id is not None:
                q = q.where(documents.c.user_id == user_id)
            return [(r[0], r[1]) for r in c.execute(q)]

    def remove_doc(self, user_id, kind, key="current"):
        with self.engine.begin() as c:
            c.execute(
                delete(documents).where(
                    documents.c.user_id == user_id, documents.c.kind == kind, documents.c.key == key
                )
            )

    def take(self, user_id, kind, key):
        with self.lock, self.engine.begin() as c:
            cond = (documents.c.user_id == user_id) & (documents.c.kind == kind) & (documents.c.key == key)
            result = c.execute(select(documents.c.payload).where(cond).with_for_update()).scalar_one_or_none()
            if result is not None:
                c.execute(delete(documents).where(cond))
            return result

    def enqueue(self, provider, payload):
        with self.engine.begin() as c:
            c.execute(
                insert(outbox).values(
                    provider=provider,
                    payload=payload,
                    status="pending",
                    attempts=0,
                    available=utcnow().timestamp(),
                    error=None,
                )
            )

    def conversation(self, user_id, conversation_id):
        with self.engine.connect() as c:
            row = (
                c.execute(
                    select(conversations).where(
                        conversations.c.user_id == user_id,
                        conversations.c.id == conversation_id,
                    )
                )
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def begin_conversation(self, user_id, conversation_id, question, context):
        try:
            with self.engine.begin() as c:
                # Serialize with account deletion so a slow answer cannot recreate deleted personal data.
                if not user_id.startswith("guest:"):
                    c.execute(select(users.c.id).where(users.c.id == user_id).with_for_update()).scalar_one()
                c.execute(
                    insert(conversations).values(
                        id=conversation_id,
                        user_id=user_id,
                        question=question,
                        created_at=utcnow().timestamp(),
                        mode="pending",
                        context=context,
                    )
                )
            return self.conversation(user_id, conversation_id), True
        except IntegrityError:
            existing = self.conversation(user_id, conversation_id)
            if not existing or existing["question"] != question:
                raise ValueError("This request ID was already used. Send a new question.") from None
            return existing, False

    def complete_conversation(self, user_id, conversation_id, response):
        with self.engine.begin() as c:
            c.execute(
                update(conversations)
                .where(
                    conversations.c.user_id == user_id,
                    conversations.c.id == conversation_id,
                    conversations.c.mode == "pending",
                )
                .values(
                    answer=response.answer,
                    gemini_answer=response.answer if response.mode == "language_service" else None,
                    completed_at=utcnow().timestamp(),
                    mode=response.mode,
                    notice=response.notice,
                    model=response.model,
                )
            )
        return self.conversation(user_id, conversation_id)

    def conversation_history(self, user_id, limit=None, before=None):
        query = select(conversations).where(conversations.c.user_id == user_id)
        if before:
            anchor = self.conversation(user_id, before)
            if not anchor:
                raise ValueError("Conversation history cursor is unavailable")
            query = query.where(
                (conversations.c.created_at < anchor["created_at"])
                | ((conversations.c.created_at == anchor["created_at"]) & (conversations.c.id < before))
            )
        with self.engine.connect() as c:
            rows = (
                c.execute(
                    query.order_by(conversations.c.created_at.desc(), conversations.c.id.desc()).limit(limit)
                )
                .mappings()
                .all()
            )
            return [dict(row) for row in reversed(rows)]

    def claim(self):
        now = utcnow().timestamp()
        with self.lock, self.engine.begin() as c:
            row = (
                c.execute(
                    select(outbox)
                    .where(outbox.c.status.in_(["pending", "processing"]), outbox.c.available <= now)
                    .order_by(outbox.c.id)
                    .with_for_update(skip_locked=True)
                    .limit(1)
                )
                .mappings()
                .first()
            )
            if not row:
                return None
            c.execute(
                update(outbox)
                .where(outbox.c.id == row["id"])
                .values(status="processing", available=now + 120)
            )
            return dict(row)

    def finish(self, job, error=None):
        with self.engine.begin() as c:
            if error is None:
                c.execute(delete(outbox).where(outbox.c.id == job["id"]))
            else:
                attempts = job["attempts"] + 1
                c.execute(
                    update(outbox)
                    .where(outbox.c.id == job["id"])
                    .values(
                        status="failed" if attempts >= 8 else "pending",
                        attempts=attempts,
                        error=error,
                        available=utcnow().timestamp() + min(300, 2**attempts),
                    )
                )

    def stats(self):
        with self.engine.connect() as c:
            return {
                "measurements": c.execute(select(func.count()).select_from(frames)).scalar(),
                "queue": dict(
                    c.execute(select(outbox.c.status, func.count()).group_by(outbox.c.status)).all()
                ),
            }

    def purge(self, days):
        cutoff = (utcnow() - timedelta(days=days)).timestamp()
        with self.engine.begin() as c:
            c.execute(delete(frames).where(frames.c.event_time < cutoff))
            c.execute(delete(conversations).where(conversations.c.created_at < cutoff))
            c.execute(delete(sessions).where(sessions.c.expires < utcnow().timestamp()))
            # Derived history also contains health data and follows the same retention horizon.
            for row in c.execute(
                select(documents).where(documents.c.kind.in_(["prediction", "readiness", "prediction_score"]))
            ).mappings():
                stamp = row["payload"].get("issued_at") or row["payload"].get("computed_at")
                if stamp and datetime.fromisoformat(stamp).timestamp() < cutoff:
                    c.execute(
                        delete(documents).where(
                            documents.c.user_id == row["user_id"],
                            documents.c.kind == row["kind"],
                            documents.c.key == row["key"],
                        )
                    )
            for row in (
                c.execute(
                    select(documents).where(
                        documents.c.kind.in_(
                            [
                                "speech",
                                "oauth_state",
                                "calendar_draft",
                                "conversation_draft",
                                "conversation_calendar_event",
                                "pending_calendar_draft",
                            ]
                        )
                    )
                )
                .mappings()
                .all()
            ):
                if row["payload"].get("expires", 0) < utcnow().timestamp():
                    c.execute(
                        delete(documents).where(
                            documents.c.user_id == row["user_id"],
                            documents.c.kind == row["kind"],
                            documents.c.key == row["key"],
                        )
                    )

    def purge_provenance(self, user_id, provenance):
        """Remove every measurement of one provenance for one user, plus the
        documents derived from history (same reasoning as purge()'s
        retention sweep: derived data carries the same taint as its source).
        Used once, to convert the demo account from synthetic to real
        Garmin data without leaving old synthetic frames mixed into its
        history or stale baselines computed from them.
        """
        with self.engine.begin() as c:
            c.execute(delete(frames).where(frames.c.user_id == user_id, frames.c.provenance == provenance))
            for kind in ["baseline", "readiness", "prediction", "prediction_score", "plan"]:
                c.execute(delete(documents).where(documents.c.user_id == user_id, documents.c.kind == kind))

    def delete_user(self, user_id):
        with self.engine.begin() as c:
            c.execute(select(users.c.id).where(users.c.id == user_id).with_for_update()).first()
            ids = {user_id}
            for identity in c.execute(
                select(documents.c.payload).where(
                    documents.c.user_id == user_id, documents.c.kind == "identity"
                )
            ).scalars():
                ids.add(identity["vendor_id"])

            def scrub(value):
                if isinstance(value, list):
                    return [clean for item in value if (clean := scrub(item)) not in [None, {}, []]]
                if isinstance(value, dict):
                    if any(value.get(k) in ids for k in ["user_id", "userId", "healthUserId"]):
                        return None
                    return {
                        k: clean for k, item in value.items() if (clean := scrub(item)) not in [None, {}, []]
                    }
                return value

            for row in c.execute(select(outbox)).mappings().all():
                clean = scrub(row["payload"])
                if not clean:
                    c.execute(delete(outbox).where(outbox.c.id == row["id"]))
                elif clean != row["payload"]:
                    c.execute(update(outbox).where(outbox.c.id == row["id"]).values(payload=clean))
            for table in [frames, documents, sessions, conversations]:
                c.execute(delete(table).where(table.c.user_id == user_id))
            c.execute(delete(users).where(users.c.id == user_id))
