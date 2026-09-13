"""Deterministic, explicitly synthetic adapter. The pipeline is identical to live ingestion."""

import asyncio
import math
from datetime import timedelta
import numpy as np
from shared.schemas import TwinFrame, SleepSummary, Provenance, utcnow


def synthetic_body_battery(stamp):
    """A plausible daily Body Battery shape: charged by morning, drained by night."""
    hour = stamp.hour + stamp.minute / 60
    return int(round(22 + 66 * math.exp(-(((hour - 8) / 7) ** 2))))


class SyntheticAdapter:
    provenance = Provenance.SYNTHETIC

    async def authorize(self, user_id):
        return {"status": "available", "provenance": self.provenance}

    async def health(self):
        return {"status": "available", "provenance": self.provenance}

    async def backfill(self, user_id, since, now=None):
        now = now or utcnow()
        rng = np.random.default_rng(42)
        days = min(28, max(1, (now - since).days))
        for ago in range(days, 0, -1):
            day = (now - timedelta(days=ago)).replace(hour=12, minute=0, second=0, microsecond=0)
            minutes = int(420 + 45 * math.sin(ago * 1.8) + rng.normal(0, 10))
            deep, rem = int(minutes * 0.22), int(minutes * 0.24)
            sleep = SleepSummary(
                start=day - timedelta(minutes=minutes + 25),
                end=day,
                total_minutes=minutes,
                awake_minutes=25,
                light_minutes=minutes - deep - rem,
                deep_minutes=deep,
                rem_minutes=rem,
            )
            yield TwinFrame(
                user_id=user_id,
                event_time=day,
                provenance=self.provenance,
                sleep=sleep,
                hrv_rmssd_ms=round(48 + 9 * math.sin(ago * 1.5), 1),
                resting_hr_bpm=round(63 + 3 * math.sin(ago), 1),
                respiration_brpm=round(14 + math.sin(ago), 1),
                spo2_pct=round(97 + math.sin(ago) * 0.6, 1),
                steps=int(7500 + 2000 * math.sin(ago)),
            )
            for hour in range(24):
                stamp = day.replace(hour=hour)
                if stamp > now:
                    continue
                yield TwinFrame(
                    user_id=user_id,
                    event_time=stamp,
                    provenance=self.provenance,
                    heart_rate_bpm=round(64 + 6 * math.sin(hour * 0.7) + rng.normal(0, 1), 1),
                    activity_level=0.05,
                    body_battery_pct=synthetic_body_battery(stamp),
                )
            for t in range(-40, 361, 10):
                tau = 103 + ago * 2
                hr = 145 + t if t < 0 else 64 + 81 * math.exp(-t / tau)
                yield TwinFrame(
                    user_id=user_id,
                    event_time=day + timedelta(hours=3, seconds=t),
                    provenance=self.provenance,
                    heart_rate_bpm=round(hr + float(rng.normal(0, 0.3)), 2),
                    activity_level=0.8 if t <= 0 else 0.03,
                )
        yield TwinFrame(
            user_id=user_id,
            event_time=now - timedelta(hours=2),
            provenance=self.provenance,
            sleep=SleepSummary(
                start=now - timedelta(hours=10),
                end=now - timedelta(hours=2),
                total_minutes=460,
                awake_minutes=20,
                light_minutes=245,
                deep_minutes=100,
                rem_minutes=115,
            ),
            hrv_rmssd_ms=58,
            resting_hr_bpm=61,
            steps=6240,
            spo2_pct=98.1,
        )

    async def stream(self, user_id):
        n = 0
        while True:
            # Full activity cycle is data generation only; avatar transitions are never scripted.
            phase = n % 720
            if phase < 120:
                hr, activity = 66 + 2 * math.sin(n / 10), 0.03
            elif phase < 180:
                hr, activity = 68 + (phase - 120) * 1.25, 0.25 + (phase - 120) / 100
            elif phase < 240:
                hr, activity = 143 + 3 * math.sin(n / 5), 0.85
            else:
                hr, activity = 64 + 80 * math.exp(-(phase - 240) / 110), 0.03
            stamp = utcnow()
            yield TwinFrame(
                user_id=user_id,
                event_time=stamp,
                provenance=self.provenance,
                heart_rate_bpm=round(hr, 1),
                respiration_brpm=round(14 + activity * 14, 1),
                activity_level=activity,
                # The watch reports Body Battery about every 5 minutes, not every second.
                body_battery_pct=synthetic_body_battery(stamp) if n % 300 == 0 else None,
            )
            n += 1
            await asyncio.sleep(1)
