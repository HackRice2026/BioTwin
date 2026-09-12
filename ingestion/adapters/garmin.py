import asyncio
import io
from datetime import datetime, timezone, timedelta
import fitdecode
from shared.schemas import TwinFrame, SleepSummary, Provenance, utcnow


def activity_level(values):
    """Derive a 0-1 movement level from the motion channels a FIT record carries.

    This is a DERIVED PROXY, not a measured quantity: FIT activity files hold no
    accelerometer, so speed and cadence stand in for movement. Recovery
    segmentation uses it only to corroborate a heart-rate decline, and the
    normalizer lowers confidence on heart rates recorded while moving. Records with
    neither channel -- strength training, for instance -- return None, and a missing
    level stays missing rather than being reported as stillness.
    """
    speed = values.get("enhanced_speed")
    if speed is None:
        speed = values.get("speed")
    if isinstance(speed, (int, float)) and speed >= 0:
        # ~4 m/s is a brisk run; above that the level is already saturated.
        return round(min(1.0, float(speed) / 4.0), 3)
    cadence = values.get("cadence")
    if isinstance(cadence, (int, float)) and cadence > 0:
        # Running cadence is reported per leg, so double it for steps per minute.
        return round(min(1.0, float(cadence) * 2 / 180.0), 3)
    return None


def parse_fit(data, user_id):
    frames = []
    with fitdecode.FitReader(io.BytesIO(data), check_crc=fitdecode.CrcCheck.RAISE) as reader:
        for message in reader:
            if not isinstance(message, fitdecode.FitDataMessage):
                continue
            values = {f.name: f.value for f in message.fields}
            stamp = values.get("timestamp")
            hr = values.get("heart_rate")
            if not isinstance(stamp, datetime) or hr is None:
                continue
            if stamp.tzinfo is None:
                stamp = stamp.replace(tzinfo=timezone.utc)
            # Only documented HR measurements are imported; vendor stress/body-battery/SDNN are not RMSSD.
            frames.append(
                TwinFrame(
                    user_id=user_id,
                    event_time=stamp,
                    provenance=Provenance.GARMIN_FIT_REPLAY,
                    heart_rate_bpm=hr,
                    activity_level=activity_level(values),
                )
            )
    if not frames:
        raise ValueError(
            "This FIT file contains no timestamped heart-rate records. Export an activity with heart-rate recording enabled."
        )
    return frames


def parse_summary(data, user_id, provenance=Provenance.GARMIN_LIVE):
    stamp = datetime.fromtimestamp(data["startTimeInSeconds"], timezone.utc)
    result = []
    for offset, hr in data.get("timeOffsetHeartRateSamples", {}).items():
        result.append(
            TwinFrame(
                user_id=user_id,
                event_time=stamp + timedelta(seconds=int(offset)),
                provenance=provenance,
                source_record_id=data.get("summaryId"),
                heart_rate_bpm=hr,
            )
        )
    values = {}
    for vendor, field in [("restingHeartRateInBeatsPerMinute", "resting_hr_bpm"), ("steps", "steps")]:
        if data.get(vendor) is not None:
            values[field] = data[vendor]
    if data.get("sleepTimeInSeconds") is not None:
        end = stamp + timedelta(seconds=data.get("durationInSeconds", data["sleepTimeInSeconds"]))
        values["sleep"] = SleepSummary(
            start=stamp,
            end=end,
            total_minutes=round(data["sleepTimeInSeconds"] / 60),
            **{
                field: round(data[vendor] / 60)
                for vendor, field in [
                    ("awakeDurationInSeconds", "awake_minutes"),
                    ("lightSleepDurationInSeconds", "light_minutes"),
                    ("deepSleepDurationInSeconds", "deep_minutes"),
                    ("remSleepInSeconds", "rem_minutes"),
                ]
                if data.get(vendor) is not None
            },
        )
        stamp = end
    if values:
        result.append(
            TwinFrame(
                user_id=user_id,
                event_time=stamp,
                provenance=provenance,
                source_record_id=data.get("summaryId"),
                **values,
            )
        )
    if not result:
        raise ValueError(
            "Garmin summary has no supported measurements; proprietary composites are not physiological fields"
        )
    return result


class GarminAdapter:
    provenance = Provenance.GARMIN_LIVE

    def __init__(self, oauth, http):
        self.oauth, self.http = oauth, http

    async def authorize(self, user_id):
        return self.oauth.start("garmin", user_id)

    async def health(self):
        return {
            "status": "configured" if self.oauth.config.garmin_client_id else "needs_credentials",
            "fallback": "garmin_fit_replay",
            "detail": "Garmin Connect Developer Program approval and OAuth credentials required for cloud sync",
        }

    async def backfill(self, user_id, since):
        token = self.oauth.token(user_id, "garmin")
        # Approved Health API: upload-time bounds, one day per request. Push notifications fetch newer data.
        for dataset in ["dailies", "sleeps"]:
            cursor = since
            while cursor < utcnow():
                end = min(cursor + timedelta(days=1), utcnow())
                response = await self.http.get(
                    f"https://apis.garmin.com/wellness-api/rest/{dataset}",
                    headers={"Authorization": f"Bearer {token}"},
                    params={
                        "uploadStartTimeInSeconds": int(cursor.timestamp()),
                        "uploadEndTimeInSeconds": int(end.timestamp()),
                    },
                )
                response.raise_for_status()
                for summary in response.json():
                    for frame in parse_summary(summary, user_id):
                        yield frame
                cursor = end

    async def stream(self, user_id):
        while True:
            async for frame in self.backfill(user_id, utcnow() - timedelta(minutes=10)):
                yield frame
            await asyncio.sleep(300)
