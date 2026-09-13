"""Give a teammate their own BioTwin login, seeded with a replay copy of the
shared team account's real Garmin/InfluxDB history, so they see real-looking
data immediately instead of an empty dashboard.

Copies frames, not access: the teammate gets their own account and their own
rows (tagged Provenance.REPLAY, never pretending to be their own live
device), so this is safe to re-run per teammate without touching anyone
else's data. Re-run it again later (same email) to refresh an existing
account with the source account's current history.

Usage:
    uv run scripts/onboard_teammate.py --email sapnil@example.com --name Sapnil
    uv run scripts/onboard_teammate.py --email sapnil@example.com --name Sapnil --password "chosen-password"
    uv run scripts/onboard_teammate.py --email sapnil@example.com --name Sapnil --source demo
"""

import argparse
import asyncio
import secrets

from core.config import Settings
from core.runtime import Runtime
from core.security import hash_password
from shared.schemas import Provenance, utcnow


async def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--password", default=None, help="Defaults to a random one, printed once.")
    parser.add_argument(
        "--source",
        default="demo",
        help="Account to replay history from (default: demo -- the shared account with DEMO_USES_REAL_DATA live Garmin/InfluxDB sync).",
    )
    args = parser.parse_args()

    runtime = Runtime(Settings())
    await runtime.start()
    try:
        store = runtime.store
        email = args.email.lower().strip()
        existing = store.by_email(email)
        if existing:
            uid = existing["id"]
            print(f"Account already exists for {email} (id={uid}); only (re)seeding data, not touching login.")
        else:
            uid = secrets.token_hex(16)
            password = args.password or secrets.token_urlsafe(12)
            store.create_user(
                uid,
                email,
                hash_password(password),
                args.name.strip() or "Your twin",
                {
                    "timezone": "America/Chicago",
                    "bedtime": "23:00",
                    "target_sleep": 480,
                    "workout_minutes": 30,
                    "naps_enabled": True,
                },
            )
            print(f"Created account for {args.name} <{email}> -- id={uid}, password={password}")

        source_history = runtime.history(args.source)
        if not source_history:
            print(f"Source account '{args.source}' has no history yet -- nothing to copy.")
            return
        copied = 0
        for frame in source_history:
            replayed = frame.model_copy(
                update={"user_id": uid, "provenance": Provenance.REPLAY, "ingest_time": utcnow()}
            )
            if await runtime.ingest(replayed, broadcast=False):
                copied += 1
        runtime.publish(uid, runtime.compute(uid, refit=True))
        print(f"Copied {copied}/{len(source_history)} frames from '{args.source}' into {uid}; baseline computed.")
    finally:
        await runtime.close()


if __name__ == "__main__":
    asyncio.run(main())
