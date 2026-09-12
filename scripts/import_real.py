"""Load a real Garmin extraction into a private account.

The default workspace is an explicitly synthetic demo. This creates a SEPARATE
real account so measurements are never mixed with synthetic readings, then bulk
imports through the same normalize/ingest path the HTTP route uses.

    uv run python -m scripts.import_real --fit ../data/garmin/fit --json raw_json

Only documented signals are imported. Nothing is inferred, nothing is filled in:
RMSSD HRV is absent from this account's exports and stays absent, which correctly
lowers readiness confidence rather than inventing a number.

The password is typed at a prompt, never passed as an argument or stored.
"""

import argparse
import asyncio
import getpass
import glob
import json
import os
import secrets
from datetime import datetime, timedelta, timezone

from ingestion.adapters.garmin import parse_fit
from ingestion.normalizer import normalize
from shared.schemas import Provenance, SleepSummary, TwinFrame, utcnow
from core.config import Settings
from core.runtime import Runtime
from core.security import hash_password


def num(v, lo=None, hi=None):
    """Garmin uses nulls and negative sentinels for "not measured"."""
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    v = float(v)
    if v <= 0:
        return None
    if lo is not None and v < lo:
        return None
    if hi is not None and v > hi:
        return None
    return v


def stamp(ms):
    return datetime.fromtimestamp(ms / 1000, timezone.utc)


def day_noon(date_str):
    """Daily summaries have no instant; anchor them at midday UTC on their own date."""
    return datetime.fromisoformat(date_str).replace(hour=12, tzinfo=timezone.utc)


def wellness_frames(root, uid):
    """Convert the raw daily payloads into TwinFrames. Daily scalars only where a
    real instant exists or the value genuinely describes the whole day."""
    out = []

    def load(name):
        path = os.path.join(root, name)
        return json.load(open(path)) if os.path.exists(path) else []

    # ---- intraday heart rate (2-minute cadence) ----
    for row in load("heart_rates.json"):
        data = row.get("data") or {}
        for sample in data.get("heartRateValues") or []:
            if isinstance(sample, list) and len(sample) > 1:
                hr = num(sample[1], 25, 250)
                if hr:
                    out.append(TwinFrame(user_id=uid, event_time=stamp(sample[0]),
                                         provenance=Provenance.GARMIN_FIT_REPLAY,
                                         heart_rate_bpm=hr, confidence=0.9))
        rhr = num(data.get("restingHeartRate"), 25, 150)
        if rhr:
            out.append(TwinFrame(user_id=uid, event_time=day_noon(row["date"]),
                                 provenance=Provenance.GARMIN_FIT_REPLAY, resting_hr_bpm=rhr))

    # ---- respiration: waking average describes the day ----
    for row in load("respiration.json"):
        data = row.get("data") or {}
        br = num(data.get("avgWakingRespirationValue"), 4, 65)
        if br:
            out.append(TwinFrame(user_id=uid, event_time=day_noon(row["date"]),
                                 provenance=Provenance.GARMIN_FIT_REPLAY, respiration_brpm=br))

    # ---- sleep: real interval, real stages ----
    for row in load("sleep.json"):
        dto = (row.get("data") or {}).get("dailySleepDTO") or {}
        total = num(dto.get("sleepTimeSeconds"))
        start_ms, end_ms = dto.get("sleepStartTimestampGMT"), dto.get("sleepEndTimestampGMT")
        if not (total and start_ms and end_ms):
            continue
        start, end = stamp(start_ms), stamp(end_ms)
        if end <= start:
            continue
        minutes = int(round(total / 60))
        span = int((end - start).total_seconds() // 60)
        if minutes > span:                       # schema requires the total to fit the interval
            minutes = span
        stages = {k: num(dto.get(v)) for k, v in
                  (("light_minutes", "lightSleepSeconds"), ("deep_minutes", "deepSleepSeconds"),
                   ("rem_minutes", "remSleepSeconds"), ("awake_minutes", "awakeSleepSeconds"))}
        stages = {k: int(round(v / 60)) for k, v in stages.items() if v is not None}
        # Stages must sum to the total or the schema rejects the record; a rounding
        # drift is corrected, a real mismatch drops the stages rather than the night.
        trio = [stages.get(k) for k in ("light_minutes", "deep_minutes", "rem_minutes")]
        if all(x is not None for x in trio) and abs(sum(trio) - minutes) > 2:
            stages = {k: v for k, v in stages.items() if k == "awake_minutes"}
        score = num(((dto.get("sleepScores") or {}).get("overall") or {}).get("value"), 0, 100)
        if score:
            stages["score"] = int(score)
        try:
            summary = SleepSummary(start=start, end=end, total_minutes=minutes, **stages)
        except ValueError:
            continue
        frame = dict(user_id=uid, event_time=end, provenance=Provenance.GARMIN_FIT_REPLAY,
                     sleep=summary)
        spo2 = num(dto.get("averageSpO2Value"), 50, 100)
        if spo2:
            frame["spo2_pct"] = spo2
        out.append(TwinFrame(**frame))

    # ---- vendor daily composites: shown with provenance, never fed to readiness ----
    for row in load("body_battery_daily.json"):
        date = row.get("date") or row.get("calendarDate")
        charged, drained = num(row.get("charged")), num(row.get("drained"))
        drained = abs(drained) if drained is not None else num(abs(row["drained"])) if row.get("drained") else None
        if date and (charged or drained):
            frame = dict(user_id=uid, event_time=day_noon(date),
                         provenance=Provenance.GARMIN_FIT_REPLAY)
            if charged:
                frame["body_battery_charged"] = int(min(100, charged))
            if drained:
                frame["body_battery_drained"] = int(min(100, drained))
            out.append(TwinFrame(**frame))

    # Intraday Body Battery. The daily charged/drained totals are summaries; this
    # is the level at a moment, which is what a forecast predicts and its
    # strongest input. Only samples Garmin marks MEASURED are taken -- MODELED and
    # UNKNOWN are its own interpolation, and importing them would make a forecast
    # partly a prediction of Garmin's guesswork.
    for row in load("stress.json"):
        for sample in (row.get("data") or {}).get("bodyBatteryValuesArray") or []:
            if not isinstance(sample, list) or len(sample) < 3 or sample[1] != "MEASURED":
                continue
            level = num(sample[2], 0, 100)
            if level is None:
                continue
            out.append(TwinFrame(user_id=uid, event_time=stamp(sample[0]),
                                 provenance=Provenance.GARMIN_FIT_REPLAY,
                                 body_battery_level=int(level)))

    for row in load("stress.json"):
        data = row.get("data") or {}
        avg, mx = num(data.get("avgStressLevel"), 0, 100), num(data.get("maxStressLevel"), 0, 100)
        if avg or mx:
            frame = dict(user_id=uid, event_time=day_noon(row["date"]),
                         provenance=Provenance.GARMIN_FIT_REPLAY)
            if avg:
                frame["stress_avg"] = int(avg)
            if mx:
                frame["stress_max"] = int(mx)
            out.append(TwinFrame(**frame))

    for row in load("stats_and_body.json"):
        data = row.get("data") or {}
        kcal = num(data.get("activeKilocalories"), 0, 20000)
        act = num(data.get("activeSeconds"), 0, 86400)
        hi = num(data.get("highlyActiveSeconds"), 0, 86400)
        floors = num(data.get("floorsAscended"), 0, 1000)
        if kcal or act or hi or floors:
            frame = dict(user_id=uid, event_time=day_noon(row["date"]),
                         provenance=Provenance.GARMIN_FIT_REPLAY)
            if kcal:
                frame["active_calories"] = int(kcal)
            if act:
                frame["active_seconds"] = int(act)
            if hi:
                frame["highly_active_seconds"] = int(hi)
            if floors:
                frame["floors_climbed"] = round(floors, 1)
            out.append(TwinFrame(**frame))

    # ---- steps ----
    for row in load("daily_steps.json"):
        steps = num(row.get("totalSteps"))
        if steps and row.get("calendarDate"):
            out.append(TwinFrame(user_id=uid, event_time=day_noon(row["calendarDate"]),
                                 provenance=Provenance.GARMIN_FIT_REPLAY, steps=int(steps)))
    return out


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", default="../data/garmin/fit", help="directory of .fit activities")
    ap.add_argument("--json", default="raw_json", help="directory of raw Garmin payloads")
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", default="Aditya")
    ap.add_argument("--timezone", default="America/Chicago")
    a = ap.parse_args()

    rt = Runtime(Settings())
    await rt.start()
    try:
        existing = rt.store.by_email(a.email.lower().strip())
        if existing:
            uid = existing["id"]
            print(f"using existing account {a.email}")
        else:
            pw = getpass.getpass(f"Set a password for {a.email} (hidden): ")
            if len(pw) < 8:
                raise SystemExit("Use at least eight characters")
            if pw != getpass.getpass("Confirm: "):
                raise SystemExit("Passwords did not match")
            uid = secrets.token_hex(16)
            rt.store.create_user(uid, a.email.lower().strip(), hash_password(pw), a.name,
                                 {"timezone": a.timezone, "bedtime": "23:00", "target_sleep": 480,
                                  "workout_minutes": 30, "naps_enabled": True,
                                  "calendar_ids": ["primary"]})
            print(f"created account {a.email}")

        frames = []
        paths = sorted(glob.glob(os.path.join(a.fit, "*.fit")))
        print(f"\nreading {len(paths)} activity files")
        for p in paths:
            try:
                got = parse_fit(open(p, "rb").read(), uid)
            except Exception as exc:
                print(f"  skipped {os.path.basename(p)}: {exc}")
                continue
            frames += got
            print(f"  {os.path.basename(p):<46} {len(got):>6} heart-rate records")

        wellness = wellness_frames(a.json, uid)
        print(f"\nwellness records from {a.json}: {len(wellness)}")
        frames += wellness

        future = [f for f in frames if f.event_time > utcnow() + timedelta(minutes=5)]
        if future:
            raise SystemExit(f"{len(future)} records are in the future; refusing the import")

        valid = []
        for f in frames:
            try:
                valid.append(normalize(f))
            except ValueError:
                pass
        print(f"validated {len(valid)} of {len(frames)} records\n")

        added = 0
        for i, f in enumerate(sorted(valid, key=lambda f: f.event_time), 1):
            added += bool(await rt.ingest(f, broadcast=False))
            if i % 5000 == 0:
                print(f"  ingested {i}/{len(valid)}")
        print(f"\nimported {added} new, {len(valid) - added} duplicates")

        state = rt.compute(uid, refit=True)
        b = state.baseline_summary
        print("\n=== baseline refitted on REAL measurements ===")
        print(f"  observations       {b.n_observations}")
        print(f"  shrinkage weight   {b.shrinkage_weight}")
        print(f"  resting HR         {b.resting_hr.median} bpm  (n_days {b.resting_hr.n_days})")
        print(f"  sleep              {b.sleep_minutes.median} min (n_days {b.sleep_minutes.n_days})")
        print(f"  respiration        {b.respiration.median} /min (n_days {b.respiration.n_days})")
        print(f"  HRV RMSSD          {b.hrv_rmssd.median} ms   (n_days {b.hrv_rmssd.n_days}) <- prior, not measured")
        print(f"  recovery tau       {b.recovery_tau_s} s  IQR {b.tau_iqr}")
        print(f"  tau sessions       {b.tau_fit_n_sessions}   held-out RMSE {b.tau_fit_rmse} bpm")
        print(f"\nlog in at http://localhost:8000 as {a.email}")
    finally:
        await rt.close()


if __name__ == "__main__":
    asyncio.run(main())
