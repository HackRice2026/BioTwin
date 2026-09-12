from datetime import datetime, timezone
from enum import StrEnum
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator

SCHEMA_VERSION = "1.0.0"


def utcnow():
    return datetime.now(timezone.utc)


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class Provenance(StrEnum):
    FITBIT_LIVE = "fitbit_live"
    FITBIT_BACKFILL = "fitbit_backfill"
    GARMIN_BLE_LIVE = "garmin_ble_live"
    GARMIN_LIVE = "garmin_live"
    GARMIN_FIT_REPLAY = "garmin_fit_replay"
    GARMIN_INFLUX_BACKFILL = "garmin_influx_backfill"
    REPLAY = "replay"
    SYNTHETIC = "synthetic"


class EnergyState(StrEnum):
    VERY_DRAINED = "very_drained"
    DRAINED = "drained"
    BELOW_AVERAGE = "below_average"
    BALANCED = "balanced"
    STRONG = "strong"
    PEAK = "peak"


class SleepSummary(Contract):
    start: AwareDatetime
    end: AwareDatetime
    total_minutes: int = Field(ge=0, le=1440)
    awake_minutes: int | None = Field(default=None, ge=0)
    light_minutes: int | None = Field(default=None, ge=0)
    deep_minutes: int | None = Field(default=None, ge=0)
    rem_minutes: int | None = Field(default=None, ge=0)
    efficiency_pct: float | None = Field(default=None, ge=0, le=100)

    @model_validator(mode="after")
    def interval(self):
        if self.end <= self.start or self.total_minutes > (self.end - self.start).total_seconds() / 60 + 1:
            raise ValueError("Sleep duration must fit its positive interval")
        stages = [self.light_minutes, self.deep_minutes, self.rem_minutes]
        if all(x is not None for x in stages) and abs(sum(stages) - self.total_minutes) > 2:
            raise ValueError("Sleep stages must sum to total sleep time")
        return self


class TwinFrame(Contract):
    user_id: str
    event_time: AwareDatetime
    ingest_time: AwareDatetime = Field(default_factory=utcnow)
    provenance: Provenance
    dedupe_key: str = ""
    sequence: int = 0
    source_record_id: str | None = None
    heart_rate_bpm: float | None = Field(default=None, ge=25, le=250)
    resting_hr_bpm: float | None = Field(default=None, ge=25, le=150)
    hrv_rmssd_ms: float | None = Field(default=None, ge=0, le=400)
    respiration_brpm: float | None = Field(default=None, ge=4, le=65)
    spo2_pct: float | None = Field(default=None, ge=50, le=100)
    activity_level: float | None = Field(default=None, ge=0, le=1)
    sleep: SleepSummary | None = None
    steps: int | None = Field(default=None, ge=0, le=200000)
    confidence: float = Field(default=1, ge=0, le=1)


class RobustStat(Contract):
    median: float
    mad: float
    p10: float
    p90: float
    n_days: int = 0


class Baseline(Contract):
    user_id: str
    computed_at: AwareDatetime
    n_observations: int
    shrinkage_weight: float
    resting_hr: RobustStat
    hrv_rmssd: RobustStat
    sleep_minutes: RobustStat
    respiration: RobustStat
    recovery_tau_s: float | None = None
    tau_fit_rmse: float | None = None
    tau_fit_n_sessions: int = 0
    tau_iqr: list[float] = Field(default_factory=list)
    cv_errors: list[float] = Field(default_factory=list)
    prior_label: str = "Engineering priors; not clinically validated"
    model_version: str = "recovery-1.0.0"


class Readiness(Contract):
    user_id: str
    computed_at: AwareDatetime
    score: float | None = Field(default=None, ge=0, le=100)
    state: EnergyState
    contributions: dict[str, float]
    confidence: float = Field(ge=0, le=1)
    degraded_reason: str | None = None
    sleep_debt_minutes: float | None = None
    cuts: list[float] = Field(default_factory=lambda: [17, 33, 50, 67, 83])


class AvatarDrivers(Contract):
    pulse_hz: float | None = None
    breath_hz: float | None = None
    fatigue: float = Field(ge=0, le=1)
    exertion: float = Field(ge=0, le=1)
    recovery_progress: float = Field(ge=0, le=1)


class CurvePoint(Contract):
    time: AwareDatetime
    value: float
    lower: float | None = None
    upper: float | None = None


class RecoveryPrediction(Contract):
    id: str
    issued_at: AwareDatetime
    horizon_s: int
    curve: list[CurvePoint]
    observed: list[CurvePoint] = Field(default_factory=list)
    rmse: float | None = None
    model_version: str = "recovery-1.0.0"
    provenance: Provenance
    assumption: str = "Assumes activity stops and recovery follows the fitted exponential."


class Proposal(Contract):
    id: str
    kind: Literal["nap", "workout"]
    title: str
    start: AwareDatetime
    end: AwareDatetime
    intensity: str
    reason: str
    score: float
    terms: dict[str, float]


class BusyInterval(Contract):
    start: AwareDatetime
    end: AwareDatetime
    title: str = "Busy"

    @model_validator(mode="after")
    def valid(self):
        if self.end <= self.start:
            raise ValueError("Invalid busy interval")
        return self


class DailyPlan(Contract):
    date: str
    timezone: str
    calendar_status: Literal["connected", "demo", "unavailable"]
    proposals: list[Proposal]
    busy: list[BusyInterval]
    explanation: str


class SimulationOverlay(Contract):
    scenario: Literal["rest", "light", "exercise"]
    label: str = "SIMULATED · illustrative assumptions, not a measured forecast"
    drivers: AvatarDrivers
    curve: list[CurvePoint]
    assumption: str


class MetricQuality(Contract):
    provenance: Provenance
    event_time: AwareDatetime
    confidence: float
    contested: bool = False
    alternatives: list[dict] = Field(default_factory=list)


class TwinState(Contract):
    schema_version: str = SCHEMA_VERSION
    sequence: int
    server_time: AwareDatetime
    readiness: Readiness
    latest: TwinFrame | None
    baseline_summary: Baseline
    drivers: AvatarDrivers
    simulation: SimulationOverlay | None = None
    provenance_banner: Provenance
    quality: dict[str, MetricQuality] = Field(default_factory=dict)
    latency_ms: float = 0
    prediction: RecoveryPrediction | None = None


class NarrationContext(Contract):
    readiness: Readiness
    baseline_summary: Baseline
    recent_trend: tuple[str, ...] = ()
    plan: DailyPlan | None = None
    prediction: RecoveryPrediction | None = None
    facts: tuple[str, ...] = ()


class NarrationResponse(Contract):
    answer: str
    mode: Literal["template", "language_service", "guard_fallback"]
    grounded: bool = True


class DayOutlook(Contract):
    issued_at: AwareDatetime
    timezone: str
    curve: list[CurvePoint]
    confidence: float
    label: str = "EXPERIMENTAL · daily readiness projection"
    assumptions: str
