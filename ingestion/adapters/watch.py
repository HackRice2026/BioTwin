"""Connect IQ wire contract. Every row retains its actual measurement timestamp."""

from datetime import timedelta

from pydantic import AwareDatetime, Field

from ingestion.normalizer import normalize
from shared.schemas import Contract, TwinFrame, Provenance, utcnow


class WatchSample(Contract):
    event_time: AwareDatetime
    heart_rate_bpm: float | None = Field(default=None, ge=25, le=250)
    steps: int | None = Field(default=None, ge=0, le=200000)
    body_battery: int | None = Field(default=None, ge=0, le=100)
    stress_level: int | None = Field(default=None, ge=0, le=100)
    spo2_pct: float | None = Field(default=None, ge=50, le=100)
    total_calories: int | None = Field(default=None, ge=0, le=30000)
    distance_m: float | None = Field(default=None, ge=0, le=500000)
    floors_climbed: float | None = Field(default=None, ge=0, le=1000)
    acceleration_mg: float | None = Field(default=None, ge=0, le=32000)


# The watch wire names stay short and stable, while BioTwin stores the same
# measurements under the canonical names already used by imports and forecasts.
WATCH_METRICS = {
    key: {"body_battery": "body_battery_pct", "distance_m": "distance_meters"}.get(key, key)
    for key in WatchSample.model_fields
    if key != "event_time"
}


class WatchBatch(Contract):
    samples: list[WatchSample] = Field(min_length=1, max_length=120)


def watch_frames(batch: WatchBatch, uid: str, retention_days: int) -> list[TwinFrame]:
    now = utcnow()
    records = []
    for sample in batch.samples:
        if not now - timedelta(days=retention_days) <= sample.event_time <= now + timedelta(minutes=5):
            raise ValueError("Watch time is outside the retention window or more than five minutes ahead")
        values = sample.model_dump(exclude_none=True)
        values = {WATCH_METRICS.get(key, key): value for key, value in values.items()}
        records.append(
            normalize(
                TwinFrame(
                    user_id=uid,
                    provenance=Provenance.GARMIN_CIQ_LIVE,
                    **values,
                )
            )
        )
    return sorted(records, key=lambda frame: frame.event_time)
