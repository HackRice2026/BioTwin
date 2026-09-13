from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Literal
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
    GARMIN_CIQ_LIVE = "garmin_ciq_live"
    GARMIN_LIVE = "garmin_live"
    GARMIN_FIT_REPLAY = "garmin_fit_replay"
    GARMIN_INFLUX_BACKFILL = "garmin_influx_backfill"
    GARMIN_INFLUX_LIVE = "garmin_influx_live"
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
    # Vendor-computed sleep score. Displayed as the vendor's own summary, never
    # treated as a measurement or blended into BioTwin's readiness.
    score: int | None = Field(default=None, ge=0, le=100)

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
    # Current watch values, distinct from daily averages, charge/drain and active calories.
    body_battery: int | None = Field(default=None, ge=0, le=100)
    stress_level: float | None = Field(default=None, ge=0, le=100)
    total_calories: int | None = Field(default=None, ge=0, le=30000)
    distance_m: float | None = Field(default=None, ge=0, le=500000)
    acceleration_mg: float | None = Field(default=None, ge=0, le=32000)
    max_hr_bpm: float | None = Field(default=None, ge=25, le=250)
    min_hr_bpm: float | None = Field(default=None, ge=25, le=250)
    distance_meters: float | None = Field(default=None, ge=0, le=100000)
    # Vendor daily summaries. These are proprietary composites, not sensor
    # measurements: they are shown with their provenance and deliberately kept out
    # of the readiness score, whose weights are a documented engineering spec.
    #
    # body_battery_pct is the intraday level, distinct from the charged/drained
    # totals beside it: Body Battery at a moment, and both what the forecast
    # predicts and its strongest input. Both branches added this field
    # independently -- dev from its InfluxDB sync, mathworks from the MEASURED
    # samples in stress.json -- so the merge keeps one field under dev's name.
    body_battery_pct: float | None = Field(default=None, ge=0, le=100)
    # Charged/drained are cumulative daily totals (can exceed a single 0-100
    # reading across multiple charge/drain cycles in a day), not a level --
    # body_battery_pct is the instantaneous level, this is the day's churn.
    # The 0-100 ceiling this branch originally gave them was wrong and would
    # have rejected valid days.
    body_battery_charged: float | None = Field(default=None, ge=0, le=300)
    body_battery_drained: float | None = Field(default=None, ge=0, le=300)
    body_battery_at_wake: float | None = Field(default=None, ge=0, le=100)
    stress_avg: int | None = Field(default=None, ge=0, le=100)
    stress_max: int | None = Field(default=None, ge=0, le=100)
    stress_high_min: float | None = Field(default=None, ge=0, le=1440)
    stress_medium_min: float | None = Field(default=None, ge=0, le=1440)
    stress_low_min: float | None = Field(default=None, ge=0, le=1440)
    active_calories: int | None = Field(default=None, ge=0, le=20000)
    active_kcal: float | None = Field(default=None, ge=0, le=20000)
    active_seconds: int | None = Field(default=None, ge=0, le=86400)
    highly_active_seconds: int | None = Field(default=None, ge=0, le=86400)
    floors_climbed: float | None = Field(default=None, ge=0, le=1000)
    floors_ascended: float | None = Field(default=None, ge=0, le=2000)
    moderate_intensity_min: float | None = Field(default=None, ge=0, le=1440)
    vigorous_intensity_min: float | None = Field(default=None, ge=0, le=1440)
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
    energy_reserve_pct: int | None = Field(default=None, ge=0, le=100)
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
    calendar: dict[str, Any] | None = None
    coach_brief: dict[str, Any] = Field(default_factory=dict)
    readiness: Readiness
    baseline_summary: Baseline
    recent_trend: tuple[str, ...] = ()
    plan: DailyPlan | None = None
    prediction: RecoveryPrediction | None = None
    facts: tuple[str, ...] = ()
    provenance: Provenance | None = None
    quality: dict[str, MetricQuality] = Field(default_factory=dict)
    # A pre-organized reading of the SAME facts above, written ahead of time by a
    # stronger model so the fast conversational model doesn't have to shape raw
    # facts into a narrative on every turn. Reading material only: narrate()'s
    # guard() refuses to resolve "briefing" as an evidence path (see
    # narration/service.py's resolve_evidence), so every number spoken still has to
    # trace back to facts/coach_brief/plan directly -- this can never become its own
    # source of truth.
    briefing: str | None = None


class NarrationResponse(Contract):
    answer: str
    mode: Literal["template", "language_service", "guard_fallback"]
    grounded: bool = True
    notice: str | None = None
    model: str | None = None


class Conversation(Contract):
    id: str
    question: str
    answer: str | None = None
    created_at: AwareDatetime
    completed_at: AwareDatetime | None = None
    mode: str
    notice: str | None = None
    model: str | None = None


class DayOutlook(Contract):
    issued_at: AwareDatetime
    timezone: str
    curve: list[CurvePoint]
    confidence: float
    label: str = "EXPERIMENTAL · daily readiness projection"
    assumptions: str
