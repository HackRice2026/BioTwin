"""Backfill from the InfluxDB the local `garmin viz dashboard` project already
fills via Garmin Connect's unofficial API. This is a *local pull*, not an
OAuth provider: no vendor token, no approved developer credentials -- it
reads a database already running on this machine. Distinct provenance
(GARMIN_INFLUX_BACKFILL) rather than reusing GARMIN_LIVE, since that value is
reserved for the approved Garmin Wellness API path GarminAdapter implements;
conflating the two would misrepresent which pipeline actually produced a
measurement.
"""

import logging
import os
from datetime import datetime, timedelta, timezone

import httpx
from pydantic import ValidationError

from shared.schemas import Provenance, SleepSummary, TwinFrame

log = logging.getLogger("biotwin")

INFLUX_HOST = os.environ.get("GARMIN_INFLUX_HOST", "localhost")
INFLUX_PORT = os.environ.get("GARMIN_INFLUX_PORT", "8086")
INFLUX_DATABASE = os.environ.get("GARMIN_INFLUX_DATABASE", "GarminStats")
INFLUX_URL = f"http://{INFLUX_HOST}:{INFLUX_PORT}/query"


def _parse_time(raw: str) -> datetime:
    return datetime.fromisoformat(raw.replace("Z", "+00:00"))


class InfluxSyncAdapter:
    """Implements ingestion.adapters.base.SourceAdapter."""

    provenance = Provenance.GARMIN_INFLUX_BACKFILL

    def __init__(self, http: httpx.AsyncClient | None = None):
        # A short-timeout client of our own: this talks to localhost only,
        # and must fail fast (not hang the request) if that stack isn't up.
        self.http = http or httpx.AsyncClient(timeout=10)

    async def authorize(self, user_id: str) -> dict:
        # No OAuth: a local database, not a vendor. Mirrors ReplayAdapter's
        # "local" status rather than returning a redirect URL.
        return {"status": "local", "provenance": self.provenance.value}

    async def health(self) -> dict:
        try:
            r = await self.http.get(
                INFLUX_URL, params={"db": INFLUX_DATABASE, "q": "SHOW MEASUREMENTS"}
            )
            r.raise_for_status()
            series = r.json().get("results", [{}])[0].get("series")
            measurements = series[0]["values"] if series else []
            return {"status": "available", "measurements": len(measurements)}
        except Exception as exc:
            return {
                "status": "unavailable",
                "detail": f"InfluxDB unreachable at {INFLUX_HOST}:{INFLUX_PORT}: {exc}",
            }

    async def _query(self, q: str) -> tuple[list[str], list[list]]:
        r = await self.http.get(INFLUX_URL, params={"db": INFLUX_DATABASE, "q": q})
        r.raise_for_status()
        result = r.json()["results"][0]
        if "error" in result:
            raise ValueError(f"InfluxDB error: {result['error']}")
        series = result.get("series")
        if not series:
            return [], []
        return series[0]["columns"], series[0]["values"]

    def _safe_frame(self, user_id: str, **kwargs) -> TwinFrame | None:
        """Garmin's own API uses sentinel values (observed: -2 on
        BreathingRate) for "not measurable" rather than omitting the field,
        which the schema's physiological bounds correctly reject. One bad
        sentinel must not abort an entire historical sync -- skip just that
        frame instead of letting a single ValidationError propagate out of
        the whole `backfill` generator and lose every frame after it.
        """
        try:
            return TwinFrame(user_id=user_id, provenance=self.provenance, **kwargs)
        except (ValidationError, ValueError) as exc:
            log.warning('{"event":"garmin_influx_skip","reason":"%s"}', exc)
            return None

    async def backfill(self, user_id: str, since: datetime):
        since_iso = since.astimezone(timezone.utc).isoformat()

        _, rows = await self._query(
            f'SELECT "HeartRate" FROM "HeartRateIntraday" WHERE time > \'{since_iso}\' ORDER BY time ASC'
        )
        for t, hr in rows:
            if hr is None:
                continue
            frame = self._safe_frame(user_id, event_time=_parse_time(t), heart_rate_bpm=hr)
            if frame:
                yield frame

        _, rows = await self._query(
            f'SELECT "restingHeartRate","totalSteps" FROM "DailyStats" '
            f"WHERE time > '{since_iso}' ORDER BY time ASC"
        )
        for t, resting, steps in rows:
            if resting is None and steps is None:
                continue
            frame = self._safe_frame(
                user_id, event_time=_parse_time(t), resting_hr_bpm=resting, steps=steps
            )
            if frame:
                yield frame

        _, rows = await self._query(
            f'SELECT "BreathingRate" FROM "BreathingRateIntraday" '
            f"WHERE time > '{since_iso}' ORDER BY time ASC"
        )
        for t, br in rows:
            if br is None:
                continue
            frame = self._safe_frame(user_id, event_time=_parse_time(t), respiration_brpm=br)
            if frame:
                yield frame

        _, rows = await self._query(
            'SELECT "sleepTimeSeconds","deepSleepSeconds","lightSleepSeconds",'
            '"remSleepSeconds","awakeSleepSeconds","averageSpO2Value" FROM "SleepSummary" '
            f"WHERE time > '{since_iso}' ORDER BY time ASC"
        )
        for t, total_s, deep_s, light_s, rem_s, awake_s, spo2 in rows:
            if total_s is None:
                continue
            end = _parse_time(t)
            try:
                # "end" is the recorded sleep-end timestamp; the real elapsed
                # interval includes awake time within the session, not just
                # time actually asleep -- matches the schema's own
                # total_minutes-excludes-awake convention (see SleepSummary's
                # validator, which sums light+deep+rem against total_minutes).
                start = end - timedelta(seconds=total_s + (awake_s or 0))
                sleep = SleepSummary(
                    start=start,
                    end=end,
                    total_minutes=round(total_s / 60),
                    deep_minutes=round(deep_s / 60) if deep_s is not None else None,
                    light_minutes=round(light_s / 60) if light_s is not None else None,
                    rem_minutes=round(rem_s / 60) if rem_s is not None else None,
                    awake_minutes=round(awake_s / 60) if awake_s is not None else None,
                )
            except (ValidationError, ValueError) as exc:
                log.warning('{"event":"garmin_influx_skip","reason":"%s"}', exc)
                continue
            frame = self._safe_frame(
                user_id,
                event_time=end,
                sleep=sleep,
                spo2_pct=spo2 if spo2 is not None and spo2 >= 50 else None,
            )
            if frame:
                yield frame

    async def stream(self, user_id: str):
        # Pull-only source (a database, not a subscription) -- live updates
        # come from the separate BLE bridge (Provenance.GARMIN_BLE_LIVE),
        # not from here. An empty async generator, not a plain function:
        # SourceAdapter.stream must be usable as `async for` by callers even
        # for a source with no live path.
        return
        yield  # pragma: no cover
