"""Revocable, ingestion-only credentials. Store hashes, never plaintext device tokens."""

import hashlib
import hmac
import secrets
from datetime import timedelta

from shared.schemas import utcnow


def issue_token(store, uid):
    token = f"{uid}.{secrets.token_urlsafe(32)}"
    expires = utcnow() + timedelta(days=90)
    store.put(
        uid,
        "watch_device",
        {
            "hash": hashlib.sha256(token.encode()).hexdigest(),
            "created_at": utcnow().isoformat(),
            "expires_at": expires.isoformat(),
            "expires": expires.timestamp(),
        },
    )
    return {"token": token, "expires_at": expires.isoformat()}


def authenticate(store, token):
    if not token or len(token) > 160 or token.count(".") != 1:
        return None
    uid, _ = token.split(".", 1)
    device = store.get(uid, "watch_device")
    if (
        not device
        or device["expires"] <= utcnow().timestamp()
        or not hmac.compare_digest(device["hash"], hashlib.sha256(token.encode()).hexdigest())
        or not store.user(uid)
    ):
        return None
    return uid
