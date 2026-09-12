import base64
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
