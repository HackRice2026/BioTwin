"""Copy one BioTwin account and its owned records from SQLite to PostgreSQL.

Usage:
    PYTHONPATH=. uv run scripts/migrate_sqlite_account.py --email user@example.com

The target database comes from ``DATABASE_URL``. The command is idempotent:
account-owned records are updated by their stable keys, while measurements are
matched by the existing per-user dedupe constraint.
"""

import argparse

from sqlalchemy import create_engine, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert

from core.config import Settings
from core.store import conversations, documents, frames, sessions, users


def owned_rows(connection, table, user_id):
    return [
        dict(row)
        for row in connection.execute(select(table).where(table.c.user_id == user_id)).mappings()
    ]


def upsert(connection, table, rows, conflict_columns, immutable_columns=()):
    if not rows:
        return 0
    statement = postgres_insert(table).values(rows)
    immutable = set(conflict_columns) | set(immutable_columns)
    updates = {
        column.name: getattr(statement.excluded, column.name)
        for column in table.columns
        if column.name not in immutable
    }
    connection.execute(
        statement.on_conflict_do_update(index_elements=list(conflict_columns), set_=updates)
    )
    return len(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--source", default="sqlite:///./data/biotwin.db")
    args = parser.parse_args()

    target_url = Settings().database_url
    if target_url.startswith("sqlite"):
        raise SystemExit("DATABASE_URL must point to PostgreSQL before running this command.")

    source_engine = create_engine(args.source)
    target_engine = create_engine(target_url, pool_pre_ping=True)
    email = args.email.lower().strip()

    with source_engine.connect() as source:
        account = source.execute(select(users).where(users.c.email == email)).mappings().first()
        if not account:
            raise SystemExit(f"No SQLite account found for {email}.")
        account = dict(account)
        user_id = account["id"]
        measurement_rows = owned_rows(source, frames, user_id)
        for row in measurement_rows:
            row.pop("id", None)
        document_rows = owned_rows(source, documents, user_id)
        session_rows = owned_rows(source, sessions, user_id)
        conversation_rows = owned_rows(source, conversations, user_id)

    with target_engine.begin() as target:
        email_owner = target.execute(
            select(users.c.id).where(users.c.email == email)
        ).scalar_one_or_none()
        if email_owner and email_owner != user_id:
            raise SystemExit(f"Target email already belongs to a different account ID: {email_owner}")

        counts = {
            "users": upsert(target, users, [account], ("id",)),
            "measurements": upsert(
                target,
                frames,
                measurement_rows,
                ("user_id", "dedupe_key"),
                ("id",),
            ),
            "documents": upsert(
                target, documents, document_rows, ("user_id", "kind", "key")
            ),
            "sessions": upsert(target, sessions, session_rows, ("hash",)),
            "conversations": upsert(target, conversations, conversation_rows, ("id",)),
        }

    source_engine.dispose()
    target_engine.dispose()
    print(
        f"Migrated {email}: "
        + ", ".join(f"{kind}={count}" for kind, count in counts.items())
    )


if __name__ == "__main__":
    main()
