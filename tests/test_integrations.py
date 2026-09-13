import base64
import hashlib
import json
import struct
import time
from datetime import datetime, timezone, timedelta
import httpx
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import hashes
from cryptography.fernet import Fernet
from core.security import TokenVault
from ingestion.adapters.fitbit import parse_google
from ingestion.adapters.garmin import parse_summary
from ingestion.webhooks import GoogleSignatureVerifier
from shared.schemas import Proposal, BusyInterval
from core.calendar import CalendarService
from pathlib import Path
from ingestion.adapters.garmin import parse_fit


def test_real_fit_decoder_and_crc_validation():
    raw = (Path(__file__).parents[1] / "fixtures/golden/generated-recovery.fit").read_bytes()
    frames = parse_fit(raw, "u")
    assert len(frames) == 37
    assert frames[0].heart_rate_bpm == 145
    assert frames[-1].heart_rate_bpm < 70
    assert frames[-1].event_time - frames[0].event_time == timedelta(seconds=360)
    corrupted = bytearray(raw)
    corrupted[-5] ^= 1
    with pytest.raises(Exception):
        parse_fit(bytes(corrupted), "u")


def test_google_parses_documented_rmssd_not_sdnn():
    sample = {
        "heartRateVariability": {
            "sampleTime": {"physicalTime": "2026-09-11T07:00:00Z"},
            "standardDeviationMilliseconds": 100,
        }
    }
    assert parse_google(sample, "heart-rate-variability", "u") is None
    sample["heartRateVariability"]["rootMeanSquareOfSuccessiveDifferencesMilliseconds"] = 42
    assert parse_google(sample, "heart-rate-variability", "u").hrv_rmssd_ms == 42
    daily = {
        "dailyHeartRateVariability": {
            "date": {"year": 2026, "month": 9, "day": 11},
            "averageHeartRateVariabilityMilliseconds": 52,
        }
    }
    assert parse_google(daily, "daily-heart-rate-variability", "u", "America/Chicago").event_time.hour == 17


def test_garmin_summary_preserves_real_samples_and_resting_rate():
    sample = {
        "startTimeInSeconds": 1789171200,
        "timeOffsetHeartRateSamples": {"0": 65, "10": 67},
        "restingHeartRateInBeatsPerMinute": 61,
        "steps": 1000,
    }
    frames = parse_summary(sample, "u")
    assert len(frames) == 3
    assert frames[1].event_time - frames[0].event_time == timedelta(seconds=10)
    assert frames[-1].resting_hr_bpm == 61
    assert all(f.hrv_rmssd_ms is None for f in frames)


def test_token_envelope_roundtrip_and_wrong_key_rejected():
    vault = TokenVault(Fernet.generate_key().decode())
    sealed = vault.seal({"access_token": "private-token"})
    assert "private-token" not in json.dumps(sealed)
    assert vault.open(sealed)["access_token"] == "private-token"
    with pytest.raises(Exception):
        TokenVault(Fernet.generate_key().decode()).open(sealed)


async def test_google_rotating_signature_is_verified_over_original_bytes():
    private = ec.generate_private_key(ec.SECP256R1())
    pub = private.public_key().public_numbers()
    encoded = b"\x1a\x20" + pub.x.to_bytes(32, "big") + b"\x22\x20" + pub.y.to_bytes(32, "big")
    async with httpx.AsyncClient() as http:
        verifier = GoogleSignatureVerifier(http)
        verifier.keys = {
            "key": [
                {"keyId": 123, "status": "ENABLED", "keyData": {"value": base64.b64encode(encoded).decode()}}
            ]
        }
        verifier.fetched = time.monotonic()
        body = b'{"data":{"operation":"UPSERT"}}'
        signature = base64.b64encode(
            b"\x01" + struct.pack(">I", 123) + private.sign(body, ec.ECDSA(hashes.SHA256()))
        ).decode()
        await verifier.verify(body, signature)
        with pytest.raises(Exception):
            await verifier.verify(body + b" ", signature)


async def test_calendar_add_includes_reminder_and_refuses_busy_slot():
    class OAuth:
        def token(self, *args):
            return "test-access"

    class Store:
        def get(self, _uid, kind, key=None):
            # add() checks connected_providers() (store "connection" docs)
            # before picking a provider to write to -- simulate Google
            # already connected, same as this test's OAuth stub assumes.
            return {"status": "connected"} if kind == "connection" and key == "google-calendar" else None

        def remove_doc(self, *args):
            pass

    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            return httpx.Response(404)
        return httpx.Response(
            200, json={"id": "created", "htmlLink": "https://calendar.google.com/calendar/event?eid=test"}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        calendar = CalendarService(OAuth(), http, Store())
        user = {"id": "u", "profile": {"timezone": "UTC"}}
        start = datetime.now(timezone.utc) + timedelta(hours=3)
        p = Proposal(
            id="p",
            kind="nap",
            title="Power nap",
            start=start,
            end=start + timedelta(minutes=20),
            intensity="rest",
            reason="Computed reason",
            score=1,
            terms={},
        )

        async def free(*args, **kwargs):
            return [], "connected"

        calendar.availability = free
        assert (await calendar.add(user, p, 15))["id"] == "created"
        body = json.loads(requests[-1].content)
        assert body["reminders"] == {"useDefault": False, "overrides": [{"method": "popup", "minutes": 15}]}
        assert "attendees" not in body

        async def occupied(*args, **kwargs):
            return [BusyInterval(start=start, end=start + timedelta(hours=1))], "connected"

        calendar.availability = occupied
        with pytest.raises(ValueError, match="now busy"):
            await calendar.add(user, p)


async def test_calendar_add_falls_back_to_microsoft_when_google_not_connected():
    class OAuth:
        def token(self, *args):
            return "test-access"

    class Store:
        def __init__(self):
            self.docs = {}

        def get(self, uid, kind, key=None):
            if kind == "connection":
                return {"status": "connected"} if key == "microsoft-calendar" else None
            return self.docs.get((uid, kind, key))

        def put(self, uid, kind, value, key=None):
            self.docs[(uid, kind, key)] = value

        def remove_doc(self, *args):
            pass

    requests = []

    def handler(request):
        requests.append(request)
        if request.method == "GET":
            # The idempotency re-check GET only finds something once an
            # event has actually been created at that vendor id.
            if request.url.path.endswith("/graph-event-1"):
                return httpx.Response(200, json={"id": "graph-event-1"})
            return httpx.Response(404)
        return httpx.Response(201, json={"id": "graph-event-1"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        store = Store()
        calendar = CalendarService(OAuth(), http, store)
        user = {"id": "u", "profile": {"timezone": "America/New_York"}}
        start = datetime.now(timezone.utc) + timedelta(hours=3)
        p = Proposal(
            id="p",
            kind="workout",
            title="Evening workout",
            start=start,
            end=start + timedelta(minutes=30),
            intensity="moderate",
            reason="Computed reason",
            score=1,
            terms={},
        )

        async def free(*args, **kwargs):
            return [], "connected"

        calendar.availability = free
        created = await calendar.add(user, p, 15)
        assert created["id"] == "graph-event-1"
        post = next(r for r in requests if r.method == "POST")
        assert post.url.path == "/v1.0/me/events"
        body = json.loads(post.content)
        assert body["subject"] == "BioTwin · Evening workout"
        assert body["isReminderOn"] is True
        assert body["reminderMinutesBeforeStart"] == 15
        assert body["start"]["timeZone"] == "America/New_York"
        # Local-time, no UTC offset suffix -- Graph's dateTimeTimeZone contract.
        assert "+" not in body["start"]["dateTime"] and "Z" not in body["start"]["dateTime"]
        assert store.get("u", "calendar_event_ref", "%s" % hashlib.sha256(b"u:p").hexdigest()[:40]) == {
            "vendor_id": "graph-event-1"
        }

        # Retrying the same proposal must not create a second event.
        requests.clear()
        again = await calendar.add(user, p, 15)
        assert again["id"] == "graph-event-1"
        assert all(r.method == "GET" for r in requests)


async def test_calendar_availability_merges_busy_across_connected_providers():
    class OAuth:
        def token(self, *args):
            return "test-access"

    class Store:
        def get(self, uid, kind, key=None):
            if kind == "connection":
                return {"status": "connected"} if key in ("google-calendar", "microsoft-calendar") else None
            return None

        def put(self, *args):
            pass

    def handler(request):
        if "googleapis.com" in str(request.url):
            return httpx.Response(
                200,
                json={
                    "calendars": {
                        "primary": {
                            "busy": [{"start": "2026-09-12T09:00:00Z", "end": "2026-09-12T10:00:00Z"}]
                        }
                    }
                },
            )
        return httpx.Response(
            200,
            json={
                "value": [
                    {
                        "start": {"dateTime": "2026-09-12T14:00:00.0000000", "timeZone": "UTC"},
                        "end": {"dateTime": "2026-09-12T15:00:00.0000000", "timeZone": "UTC"},
                        "showAs": "busy",
                    },
                    {
                        "start": {"dateTime": "2026-09-12T16:00:00.0000000", "timeZone": "UTC"},
                        "end": {"dateTime": "2026-09-12T17:00:00.0000000", "timeZone": "UTC"},
                        "showAs": "free",
                    },
                ]
            },
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        calendar = CalendarService(OAuth(), http, Store())
        user = {"id": "u", "profile": {"timezone": "UTC"}}
        busy, status = await calendar.availability(user, force=True)
        assert status == "connected"
        # One busy block from Google, one from Microsoft -- the "free"
        # Microsoft entry must be excluded by the showAs filter.
        assert len(busy) == 2
        assert {b.start.hour for b in busy} == {9, 14}


async def test_seed_refuses_when_calendar_already_has_events():
    class OAuth:
        def token(self, *args):
            return "test-access"

    class Store:
        def get(self, uid, kind, key=None):
            if kind == "connection":
                return {"status": "connected"} if key == "google-calendar" else None
            return None

    def handler(request):
        # Any freeBusy check comes back with one existing event.
        return httpx.Response(
            200,
            json={"calendars": {"primary": {"busy": [{"start": "2026-09-14T09:00:00Z", "end": "2026-09-14T10:00:00Z"}]}}},
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        calendar = CalendarService(OAuth(), http, Store())
        user = {"id": "u", "profile": {"timezone": "UTC"}}
        result = await calendar.seed_if_empty(user)
        assert result == {"seeded": False, "created": 0, "reason": "Your calendar already has events in the next week"}


async def test_seed_writes_a_full_week_when_calendar_is_empty():
    class OAuth:
        def token(self, *args):
            return "test-access"

    class Store:
        def get(self, uid, kind, key=None):
            if kind == "connection":
                return {"status": "connected"} if key == "google-calendar" else None
            return None

        def remove_doc(self, *args):
            pass

    posts = []

    def handler(request):
        if request.method == "GET":
            return httpx.Response(404)
        if "freeBusy" in str(request.url):
            return httpx.Response(200, json={"calendars": {"primary": {"busy": []}}})
        posts.append(request)
        return httpx.Response(200, json={"id": f"created-{len(posts)}"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        calendar = CalendarService(OAuth(), http, Store())
        user = {"id": "u", "profile": {"timezone": "UTC"}}
        result = await calendar.seed_if_empty(user)
        assert result["seeded"] is True
        # Every event has an "id"/"summary"/no fabricated wellness description --
        # this is a Google Calendar event body, not a wellness-plan one.
        assert len(posts) == result["created"] > 0
        bodies = [json.loads(p.content) for p in posts]
        assert all("summary" in b and b["summary"] for b in bodies)
        titles = {b["summary"] for b in bodies}
        # At least one class, one work block, one meeting/club made it through.
        assert any("Class" in t for t in titles)
        assert any("Work" in t for t in titles)
        assert any("Office hours" in t or "Club" in t for t in titles)
