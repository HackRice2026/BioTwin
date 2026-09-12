import hashlib
import json
from datetime import timezone
from shared.schemas import TwinFrame

METRICS = (
    "heart_rate_bpm",
    "resting_hr_bpm",
    "hrv_rmssd_ms",
    "respiration_brpm",
    "spo2_pct",
    "activity_level",
    "sleep",
    "steps",
    "max_hr_bpm",
    "min_hr_bpm",
    "distance_meters",
    "floors_ascended",
    "active_kcal",
    "body_battery_pct",
    "stress_level",
    "stress_high_min",
    "stress_medium_min",
    "stress_low_min",
    "body_battery_charged",
    "body_battery_drained",
    "body_battery_at_wake",
    "moderate_intensity_min",
    "vigorous_intensity_min",
)


def normalize(raw: dict | TwinFrame) -> TwinFrame:
    frame = raw if isinstance(raw, TwinFrame) else TwinFrame.model_validate(raw)
    present = {k: getattr(frame, k) for k in METRICS if getattr(frame, k) is not None}
    if not present:
        raise ValueError("Measurement has no supported physiological fields")
    # Value fingerprint preserves vendor corrections as revisions while identical deliveries deduplicate.
    identity = {
        "user": frame.user_id,
        "source": frame.provenance.value.replace("_backfill", "_live"),
        "time": frame.event_time.astimezone(timezone.utc).isoformat(),
        "metrics": present,
    }
    key = hashlib.sha256(json.dumps(identity, sort_keys=True, default=str).encode()).hexdigest()
    confidence = frame.confidence
    if frame.heart_rate_bpm is not None and (frame.activity_level or 0) > 0.5:
        confidence = min(confidence, 0.75)
    return frame.model_copy(
        update={
            "dedupe_key": key,
            "confidence": confidence,
            "event_time": frame.event_time.astimezone(timezone.utc),
            "sequence": 0,
        }
    )
