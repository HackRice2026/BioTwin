import hashlib
import importlib.util
from datetime import timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from core.api import create_app
from core.config import Settings
from shared.schemas import utcnow


@pytest.fixture
def client(tmp_path):
    with TestClient(
        create_app(
            Settings(_env_file=None, database_url=f"sqlite:///{tmp_path}/watch.db", demo_enabled=False)
        )
    ) as client:
        yield client


def register(client, email="watch@example.com"):
    result = client.post(
        "/auth/session/register",
        json={
            "email": email,
            "name": "Watch test",
            "adult": True,
            "password": "test-watch-password",
        },
    )
    assert result.status_code == 200
    return result.json()["user"]["id"]


def pair(client):
    uid = register(client)
    response = client.post("/api/watch/token")
    assert response.status_code == 200
    return uid, {"x-api-key": response.json()["token"]}


def batch(**kwargs):
    return {"samples": [{"event_time": utcnow().isoformat(), **kwargs}]}


def test_watch_auth_scope_rotation_revocation_expiry_and_no_plaintext(client):
    assert client.post("/api/watch/token").status_code == 401
    uid, headers = pair(client)
    token = headers["x-api-key"]
    device = client.app.state.runtime.store.get(uid, "watch_device")
    assert token not in str(device)
    assert device["hash"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in client.get("/api/watch").text
    payload = batch(heart_rate_bpm=80)
    assert client.post("/api/ingest/watch", json=payload).status_code == 401  # Cookie is insufficient.
    client.post("/auth/session/logout")
    assert client.get("/api/state", headers=headers).status_code == 401
    assert client.post("/api/watch/token", headers=headers).status_code == 401
    assert client.post("/api/ingest/watch", json=payload, headers=headers).status_code == 200
    client.post("/auth/session/login", json={"email": "watch@example.com", "password": "test-watch-password"})
    new_headers = {"x-api-key": client.post("/api/watch/token").json()["token"]}
    assert client.post("/api/ingest/watch", json=payload, headers=headers).status_code == 401
    assert client.post("/api/ingest/watch", json=payload, headers=new_headers).status_code == 200
    device = client.app.state.runtime.store.get(uid, "watch_device")
    client.app.state.runtime.store.put(uid, "watch_device", {**device, "expires": 0})
    assert client.post("/api/ingest/watch", json=payload, headers=new_headers).status_code == 401
    new_headers = {"x-api-key": client.post("/api/watch/token").json()["token"]}
    assert client.delete("/api/watch/token").status_code == 200
    assert client.post("/api/ingest/watch", json=payload, headers=new_headers).status_code == 401


def test_watch_partial_metrics_dedupe_original_times_and_websocket(client):
    uid, headers = pair(client)
    now = utcnow()
    old = now - timedelta(minutes=20)
    payload = {
        "samples": [
            {"event_time": now.timestamp(), "heart_rate_bpm": 84, "steps": 0, "total_calories": 1500},
            {"event_time": old.timestamp(), "stress_level": 0, "body_battery": 72, "spo2_pct": 97},
            {"event_time": now.timestamp(), "acceleration_mg": 1001, "distance_m": 0, "floors_climbed": 0},
        ]
    }
    with client.websocket_connect("/ws/live", headers={"origin": "http://localhost:5173"}) as ws:
        ws.send_json({"type": "hello", "last_sequence": 0})
        ws.receive_json()
        result = client.post("/api/ingest/watch", json=payload, headers=headers)
        assert result.status_code == 200, result.text
        assert result.json() == {"accepted": 3, "duplicates": 0, "sequence": 3}
        pushed = ws.receive_json()["payload"]
        assert pushed["latest"]["heart_rate_bpm"] == 84
        assert pushed["drivers"]["pulse_hz"] == 1.4
        assert pushed["quality"]["body_battery_pct"]["event_time"] == old.isoformat().replace(
            "+00:00", "Z"
        )
        assert pushed["latest"]["body_battery_pct"] == 72
        assert pushed["latest"]["distance_meters"] == 0
        assert pushed["readiness"]["user_id"] == uid
        assert pushed["readiness"]["score"] is None  # No invented HRV/sleep inputs.
        assert pushed["latest"]["active_calories"] is None
        assert pushed["latest"]["body_battery_drained"] is None
    result = client.post("/api/ingest/watch", json=payload, headers=headers)
    assert result.json() == {"accepted": 0, "duplicates": 3, "sequence": 3}
    frames = client.get("/api/data/export").json()["frames"]
    assert len(frames) == 3
    assert all(f["provenance"] == "garmin_ciq_live" and f["user_id"] == uid for f in frames)
    assert client.get("/api/watch").json()["readings"]["steps"]["value"] == 0
    correction = {"samples": [{**payload["samples"][1], "body_battery": 73}]}
    assert client.post("/api/ingest/watch", json=correction, headers=headers).json()["accepted"] == 1
    assert client.get("/api/watch").json()["readings"]["body_battery"]["value"] == 73


@pytest.mark.parametrize(
    "bad",
    [
        {"heart_rate_bpm": 999},
        {"stress_level": -1},
        {"body_battery": 101},
        {"spo2_pct": 101},
        {"steps": -1},
        {"acceleration_mg": 99999},
        {"total_calories": 30001},
        {"steps": 1.5},
        {"event_time": "2026-01-01T12:00:00"},
        {"event_time": "2099-01-01T00:00:00Z"},
        {"event_time": "2000-01-01T00:00:00Z"},
        {"user_id": "victim"},
        {"hrv_rmssd_ms": 45},
        {"provenance": "garmin_ble_live"},
        {"heart_rate_bpm": None},
    ],
)
def test_watch_invalid_batch_commits_nothing(client, bad):
    _, headers = pair(client)
    payload = {
        "samples": [batch(heart_rate_bpm=80)["samples"][0], {"event_time": utcnow().isoformat(), **bad}]
    }
    result = client.post("/api/ingest/watch", json=payload, headers=headers)
    assert result.status_code == 422, result.text
    assert client.get("/api/data/export").json()["frames"] == []


def test_watch_limits_and_isolation_and_account_deletion(client):
    a, headers = pair(client)
    assert client.post("/api/ingest/watch", json={"samples": []}, headers=headers).status_code == 422
    payload = batch(steps=100)
    assert (
        client.post(
            "/api/ingest/watch", json={"samples": payload["samples"] * 121}, headers=headers
        ).status_code
        == 422
    )
    assert client.post("/api/ingest/watch", json=payload, headers=headers).status_code == 200
    client.post("/auth/session/logout")
    b = register(client, "second@example.com")
    assert a != b
    assert client.get("/api/watch").json()["readings"] == {}
    assert client.post("/api/ingest/watch", json=batch(steps=101), headers=headers).status_code == 200
    assert client.get("/api/state").json()["latest"] is None
    client.post("/auth/session/logout")
    client.post("/auth/session/login", json={"email": "watch@example.com", "password": "test-watch-password"})
    for _ in range(28):
        assert client.post("/api/ingest/watch", json=payload, headers=headers).status_code == 200
    assert client.post("/api/ingest/watch", json=payload, headers=headers).status_code == 429
    assert client.delete("/api/data").status_code == 200
    assert client.post("/api/ingest/watch", json=payload, headers=headers).status_code == 401


def test_watch_source_precedence_and_composites_do_not_change_readiness(client):
    _, headers = pair(client)
    client.post("/api/ingest/bluetooth", json={"heart_rate_bpm": 80})
    before = client.get("/api/state").json()
    client.post(
        "/api/ingest/watch", json=batch(heart_rate_bpm=90, stress_level=99, body_battery=1), headers=headers
    )
    after = client.get("/api/state").json()
    assert after["quality"]["heart_rate_bpm"]["provenance"] == "garmin_ble_live"
    assert after["readiness"]["score"] == before["readiness"]["score"]


def test_config_generator_rejects_unsafe_url_and_protects_key(tmp_path):
    path = Path(__file__).parents[1] / "watch-app/scripts/configure.py"
    spec = importlib.util.spec_from_file_location("watch_configure", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    env, out = tmp_path / ".env", tmp_path / "ApiConfig.mc"
    key = "a" * 32 + "." + "b" * 43
    env.write_text(f"API_URL=https://example.com/api/ingest/watch\nAPI_KEY={key}\n")
    module.generate(env, out)
    assert out.stat().st_mode & 0o777 == 0o600
    assert key in out.read_text()
    env.write_text(f"API_URL=http://example.com/api/ingest/watch\nAPI_KEY={key}\n")
    with pytest.raises(ValueError, match="HTTPS"):
        module.generate(env, out)


def test_config_generator_accepts_key_file_without_env(tmp_path):
    path = Path(__file__).parents[1] / "watch-app/scripts/configure.py"
    spec = importlib.util.spec_from_file_location("watch_configure_key_file", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    key = "a" * 32 + "." + "b" * 43
    key_file, out = tmp_path / "watch.token", tmp_path / "ApiConfig.mc"
    key_file.write_text(key + "\n")
    module.generate(
        tmp_path / "missing.env",
        out,
        api_url="https://example.com/api/ingest/watch",
        api_key_file=key_file,
        send_interval=7,
    )
    content = out.read_text()
    assert key in content
    assert 'API_URL = "https://example.com/api/ingest/watch"' in content
    assert "SEND_INTERVAL_SECONDS = 7" in content
