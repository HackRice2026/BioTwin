"""Pull the newest Garmin measurements and ingest them, in one command.

Run this right before recording. It uses the cached Garmin tokens, so it needs no
password, and it is safe to run repeatedly: identical readings deduplicate.

    uv run python -m scripts.refresh_garmin --email you@example.com --days 3

The dashboard is only as fresh as your last Garmin Connect sync. Open Garmin
Connect on your phone first and let the watch sync, or this pulls yesterday again.

Requires the unofficial client, installed as a local tool rather than a project
dependency: `./.venv/bin/python -m pip install garminconnect`. This is a personal
export path, not the approved Garmin Connect Developer integration the README
describes, and it reads only the operator's own account.
"""

import argparse
import asyncio
import datetime as dt
import json
import os
import time

from garminconnect import Garmin, GarminConnectTooManyRequestsError

from core.config import Settings
from core.runtime import Runtime
from ingestion.normalizer import normalize
from scripts.import_real import wellness_frames

RAW = "raw_json"


def probe(fn, pause=0.25):
    try:
        return fn()
    except GarminConnectTooManyRequestsError:
        print("  rate limited, waiting 20 s")
        time.sleep(20)
        return None
    except Exception:
        return None
    finally:
        time.sleep(pause)


def merge(name, fresh, key):
    """Replace the rows for the pulled dates, keep the rest of the history."""
    path = os.path.join(RAW, name)
    old = json.load(open(path)) if os.path.exists(path) else []
    dates = {r.get(key) for r in fresh if r.get(key)}
    kept = [r for r in old if r.get(key) not in dates]
    merged = sorted(kept + fresh, key=lambda r: str(r.get(key)))
    json.dump(merged, open(path, "w"), indent=1, default=str)
    return len(fresh), len(merged)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--email", required=True, help="your BioTwin account")
    ap.add_argument("--days", type=int, default=3, help="how many recent days to re-pull")
    a = ap.parse_args()

    api = Garmin()
    api.login("~/.garminconnect")
    today = dt.date.today()
    days = [(today - dt.timedelta(days=i)).isoformat() for i in range(a.days)]
    print(f"pulling {days[-1]} .. {days[0]}\n")

    per_day = {
        "heart_rates.json": lambda d: api.get_heart_rates(d),
        "sleep.json": lambda d: api.get_sleep_data(d),
        "respiration.json": lambda d: api.get_respiration_data(d),
        "stress.json": lambda d: api.get_stress_data(d),
        "all_day_stress.json": lambda d: api.get_all_day_stress(d),
        "stats_and_body.json": lambda d: api.get_stats_and_body(d),
    }
    for name, call in per_day.items():
        fresh = [{"date": d, "data": r} for d in days if (r := probe(lambda: call(d)))]
        got, total = merge(name, fresh, "date")
        print(f"  {name:<24} {got} fresh, {total} total")

    steps = probe(lambda: api.get_daily_steps(days[-1], days[0])) or []
    got, total = merge("daily_steps.json", steps, "calendarDate")
    print(f"  {'daily_steps.json':<24} {got} fresh, {total} total")

    bb = probe(lambda: api.get_body_battery(days[-1], days[0])) or []
    got, total = merge("body_battery_daily.json", bb, "date")
    print(f"  {'body_battery_daily.json':<24} {got} fresh, {total} total")

    # New activities, as original .FIT
    acts = probe(lambda: api.get_activities(0, 12)) or []
    fitdir = os.path.join("..", "data", "garmin", "fit")
    os.makedirs(fitdir, exist_ok=True)
    new_fit = []
    for act in acts:
        if (act.get("duration") or 0) < 300:
            continue
        stamp = str(act.get("startTimeLocal", act["activityId"])).replace(":", "-").replace(" ", "_")
        kind = (act.get("activityType") or {}).get("typeKey", "activity")
        target = os.path.join(fitdir, f"{stamp}_{kind}.fit")
        if os.path.exists(target):
            continue
        blob = probe(lambda: api.download_activity(
            act["activityId"], dl_fmt=api.ActivityDownloadFormat.ORIGINAL), pause=0.4)
        if not blob:
            continue
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                for member in z.namelist():
                    if member.lower().endswith(".fit"):
                        open(target, "wb").write(z.read(member))
                        new_fit.append(target)
        except zipfile.BadZipFile:
            open(target, "wb").write(blob)
            new_fit.append(target)
    print(f"\n  new activity files: {len(new_fit)}")
    for f in new_fit:
        print(f"    {os.path.basename(f)}")

    # ---- ingest ----
    rt = Runtime(Settings())
    await rt.start()
    try:
        user = rt.store.by_email(a.email.lower().strip())
        if not user:
            raise SystemExit(f"no account for {a.email}")
        uid = user["id"]
        frames = wellness_frames(RAW, uid)
        if new_fit:
            from ingestion.adapters.garmin import parse_fit
            for f in new_fit:
                frames += parse_fit(open(f, "rb").read(), uid)
        valid = []
        for f in frames:
            try:
                valid.append(normalize(f))
            except ValueError:
                pass
        added = 0
        for f in sorted(valid, key=lambda f: f.event_time):
            added += bool(await rt.ingest(f, broadcast=False))
        print(f"\ningested {added} new readings ({len(valid) - added} already present)")

        state = rt.compute(uid, refit=True)
        now = dt.datetime.now(dt.timezone.utc)
        print("\n=== FRESHNESS OF EACH DASHBOARD TILE ===")
        for metric, q in sorted(state.quality.items(), key=lambda kv: kv[1].event_time, reverse=True):
            age = (now - q.event_time).total_seconds() / 3600
            mark = "TODAY" if age < 24 else ("yesterday" if age < 48 else f"{age/24:.0f} days old")
            print(f"  {metric:<20} {q.event_time.astimezone():%b %d %I:%M %p}   {mark}")
        rt.publish(uid, state)
    finally:
        await rt.close()


if __name__ == "__main__":
    asyncio.run(main())
