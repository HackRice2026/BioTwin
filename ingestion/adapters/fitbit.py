import asyncio
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from shared.schemas import TwinFrame, SleepSummary, Provenance

GOOGLE_TYPES = {
    "heart-rate": ("heartRate", "beatsPerMinute", "heart_rate_bpm"),
    "heart-rate-variability": (
        "heartRateVariability",
        "rootMeanSquareOfSuccessiveDifferencesMilliseconds",
        "hrv_rmssd_ms",
    ),
    "daily-heart-rate-variability": (
        "dailyHeartRateVariability",
        "averageHeartRateVariabilityMilliseconds",
        "hrv_rmssd_ms",
    ),
    "daily-resting-heart-rate": ("dailyRestingHeartRate", "beatsPerMinute", "resting_hr_bpm"),
    "daily-respiratory-rate": ("dailyRespiratoryRate", "breathsPerMinute", "respiration_brpm"),
    "daily-oxygen-saturation": ("dailyOxygenSaturation", "averagePercentage", "spo2_pct"),
    "steps": ("steps", "count", "steps"),
    "sleep": ("sleep", None, "sleep"),
    "activity-level": ("activityLevel", "activityLevelType", "activity_level"),
}


def parse_google(point, data_type, user_id, tz="UTC", provenance=Provenance.FITBIT_LIVE):
    key, value_key, metric = GOOGLE_TYPES[data_type]
    obj = point[key]
    interval = obj.get("interval", {})
    stamp = obj.get("sampleTime", {}).get("physicalTime") or interval.get("endTime")
    if stamp:
        stamp = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    elif "date" in obj:
        d = obj["date"]
        stamp = datetime(d["year"], d["month"], d["day"], 12, tzinfo=ZoneInfo(tz)).astimezone(timezone.utc)
    else:
        raise ValueError("Google data point is missing its measurement timestamp")
    value = obj.get(value_key) if value_key else None
    if data_type == "sleep":
        summary = obj.get("summary", {})
        if "minutesAsleep" not in summary:
            raise ValueError("Sleep summary is not yet processed by the vendor")
        stages = {
            x["type"].lower() + "_minutes": int(x["minutes"])
            for x in summary.get("stagesSummary", [])
            if x["type"] in ["AWAKE", "LIGHT", "DEEP", "REM"]
        }
        value = SleepSummary(
            start=interval["startTime"],
            end=interval["endTime"],
            total_minutes=int(summary["minutesAsleep"]),
            **stages,
        )
    elif data_type == "activity-level":
        value = {"SEDENTARY": 0, "LIGHTLY_ACTIVE": 0.3, "MODERATELY_ACTIVE": 0.6, "VERY_ACTIVE": 0.9}.get(
            value
        )
    if value is None:
        return None
    return TwinFrame(
        user_id=user_id,
        event_time=stamp,
        provenance=provenance,
        source_record_id=point.get("name"),
        **{metric: value},
    )


class FitbitAdapter:
    provenance = Provenance.FITBIT_LIVE

    def __init__(self, oauth, http):
        self.oauth, self.http = oauth, http

    async def authorize(self, user_id):
        return self.oauth.start("fitbit", user_id)

    async def health(self):
        return {"status": "configured" if self.oauth.config.google_client_id else "needs_credentials"}

    async def fetch(self, user_id, since, data_types=None, live=False):
        token = self.oauth.token(user_id, "fitbit")
        tz = self.oauth.store.user(user_id)["profile"].get("timezone", "UTC")
        for data_type in data_types or GOOGLE_TYPES:
            if data_type not in GOOGLE_TYPES:
                continue
            field = data_type.replace("-", "_")
            time_field = (
                "date"
                if data_type.startswith("daily-")
                else "interval.end_time"
                if data_type in ["steps", "sleep", "activity-level"]
                else "sample_time.physical_time"
            )
            date = (
                since.astimezone(ZoneInfo(tz)).strftime("%Y-%m-%d")
                if time_field == "date"
                else since.isoformat()
            )
            params = {"filter": f'{field}.{time_field} >= "{date}"', "pageSize": 1000}
            while True:
                r = await self.http.get(
                    f"https://health.googleapis.com/v4/users/me/dataTypes/{data_type}/dataPoints",
                    headers={"Authorization": f"Bearer {token}"},
                    params=params,
                )
                r.raise_for_status()
                payload = r.json()
                for point in payload.get("dataPoints", []):
                    frame = parse_google(
                        point,
                        data_type,
                        user_id,
                        tz,
                        Provenance.FITBIT_LIVE if live else Provenance.FITBIT_BACKFILL,
                    )
                    if frame:
                        yield frame
                if not payload.get("nextPageToken"):
                    break
                params["pageToken"] = payload["nextPageToken"]

    async def backfill(self, user_id, since):
        async for f in self.fetch(user_id, since):
            yield f

    async def stream(self, user_id):
        from shared.schemas import utcnow
        from datetime import timedelta

        while True:
            async for f in self.fetch(user_id, utcnow() - timedelta(minutes=10), live=True):
                yield f
            await asyncio.sleep(300)
