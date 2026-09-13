"""Copy one account's history from the local SQLite file into the shared Postgres.

Written to be re-runnable: every insert is ON CONFLICT DO NOTHING against the
(user_id, dedupe_key) uniqueness the store already enforces, so a second run
adds nothing and a failed run can simply be repeated.

Two things are deliberately NOT copied:

  token and connection documents. They hold the sealed OAuth credential for
  Google Calendar. The seal is only as private as TOKEN_ENCRYPTION_KEY, and a
  team that shares one .env shares that key -- copying those rows into a shared
  database would hand calendar read and write access to anyone holding the
  connection string. Reconnect per deployment instead.

  oauth_state. Single-use, expires in ten minutes, meaningless elsewhere.

    ./.venv/bin/python -m scripts.migrate_to_postgres --email you@example.com
    ./.venv/bin/python -m scripts.migrate_to_postgres --email you@example.com --also-demo
"""

import argparse
import json

from sqlalchemy import create_engine, text
from sqlalchemy.dialects.postgresql import insert as pg_insert

from core.config import Settings
from core.store import Store, documents, frames, users

SECRET_KINDS = {"token", "connection", "oauth_state"}
BATCH = 500


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True)
    ap.add_argument("--source", default="sqlite:///./data/biotwin.db")
    ap.add_argument("--target", default=None, help="defaults to DATABASE_URL")
    ap.add_argument(
        "--also-demo",
        action="store_true",
        help="mirror the same history onto the demo account, so the app shows "
             "real data with no sign-in. Replaces the demo's synthetic frames.",
    )
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    target_url = a.target or Settings().database_url
    if target_url.startswith("sqlite"):
        raise SystemExit("Target is SQLite; nothing to migrate. Set DATABASE_URL or pass --target.")
    print(f"source: {a.source}\ntarget: {target_url.split('@')[-1]}\n")

    source = Store(a.source)
    target = create_engine(target_url, pool_pre_ping=True)

    with source.engine.connect() as src:
        user = src.execute(
            text("select id, email, password, name, profile, sequence from users where email = :e"),
            {"e": a.email.lower().strip()},
        ).mappings().first()
        if not user:
            raise SystemExit(f"no local account for {a.email}")
        uid = user["id"]
        total = src.execute(
            text("select count(*) from measurements where user_id = :u"), {"u": uid}
        ).scalar()
    print(f"account {a.email}  id={uid}\nlocal measurements: {total}\n")

    if a.dry_run:
        print("dry run: nothing written")
        return

    profile = user["profile"]
    if isinstance(profile, str):
        profile = json.loads(profile)

    targets = [uid] + (["demo"] if a.also_demo else [])

    with target.begin() as dst:
        # The account itself. An existing row is left alone: a teammate may have
        # set their own profile, and this migration is about history, not identity.
        dst.execute(
            pg_insert(users)
            .values(
                id=uid,
                email=user["email"],
                password=user["password"],
                name=user["name"],
                profile=profile,
                sequence=user["sequence"],
            )
            .on_conflict_do_nothing(index_elements=["id"])
        )
        if a.also_demo:
            # The demo carries synthetic frames by default. Mixing real and
            # synthetic under one account would put "synthetic" provenance
            # badges beside real readings, so the synthetic ones go first.
            removed = dst.execute(
                text("delete from measurements where user_id = 'demo' and provenance = 'synthetic'")
            ).rowcount
            dst.execute(
                text("delete from documents where user_id = 'demo' and kind in "
                     "('baseline', 'readiness', 'prediction', 'prediction_score', 'plan')")
            )
            print(f"demo: removed {removed} synthetic frames and their derived documents")

    copied = {t: 0 for t in targets}
    with source.engine.connect() as src:
        rows = src.execute(
            text("select event_time, ingest_time, provenance, dedupe_key, sequence, payload "
                 "from measurements where user_id = :u order by event_time"),
            {"u": uid},
        )
        batch = []
        for row in rows.mappings():
            payload = row["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            batch.append(dict(row) | {"payload": payload})
            if len(batch) >= BATCH:
                _flush(target, batch, targets, copied, total)
                batch = []
        if batch:
            _flush(target, batch, targets, copied, total)

    with source.engine.connect() as src:
        docs = src.execute(
            text("select kind, key, payload from documents where user_id = :u"), {"u": uid}
        ).mappings().all()
    kept = [d for d in docs if d["kind"] not in SECRET_KINDS]
    skipped = [d["kind"] for d in docs if d["kind"] in SECRET_KINDS]
    with target.begin() as dst:
        for doc in kept:
            payload = doc["payload"]
            if isinstance(payload, str):
                payload = json.loads(payload)
            for t in targets:
                dst.execute(
                    pg_insert(documents)
                    .values(user_id=t, kind=doc["kind"], key=doc["key"], payload=payload)
                    .on_conflict_do_update(
                        index_elements=["user_id", "kind", "key"], set_={"payload": payload}
                    )
                )

    print("\n--- done ---")
    with target.connect() as dst:
        for t in targets:
            present = dst.execute(
                text("select count(*) from measurements where user_id = :u"), {"u": t}
            ).scalar()
            print(f"  {t[:12]:14} rows now present: {present}  (local source has {total})")
    print(f"  documents copied: {len(kept) * len(targets)}")
    if skipped:
        print(f"  documents deliberately skipped (credentials): {sorted(set(skipped))}")

    with target.connect() as dst:
        for row in dst.execute(text(
            "select u.email, count(m.id) from users u left join measurements m "
            "on m.user_id = u.id group by u.email order by 2 desc")):
            print(f"  target now: {row[0]:28} {row[1]}")


def _flush(target, batch, targets, copied, total):
    with target.begin() as dst:
        for t in targets:
            statement = pg_insert(frames).values([
                {
                    "user_id": t,
                    "event_time": r["event_time"],
                    "ingest_time": r["ingest_time"],
                    "provenance": r["provenance"],
                    "dedupe_key": r["dedupe_key"],
                    "sequence": r["sequence"],
                    "payload": r["payload"],
                }
                for r in batch
            ]).on_conflict_do_nothing(index_elements=["user_id", "dedupe_key"])
            copied[t] += dst.execute(statement).rowcount or 0
    copied["_seen"] = copied.get("_seen", 0) + len(batch)
    print(f"  sent {copied['_seen']}/{total} rows", end="\r", flush=True)


if __name__ == "__main__":
    main()
