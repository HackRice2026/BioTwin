/* Generated from shared/schemas. Run npm run types. Do not edit. */

export type EnergyReservePct = number | null;
export type SchemaVersion = string;
export type Sequence = number;
export type ServerTime = string;
export type UserId = string;
export type ComputedAt = string;
export type Score = number | null;
export type EnergyState = "very_drained" | "drained" | "below_average" | "balanced" | "strong" | "peak";
export type Confidence = number;
export type DegradedReason = string | null;
export type SleepDebtMinutes = number | null;
export type Cuts = number[];
export type UserId1 = string;
export type EventTime = string;
export type IngestTime = string;
export type Provenance =
  | "fitbit_live"
  | "fitbit_backfill"
  | "garmin_ble_live"
  | "garmin_ciq_live"
  | "garmin_live"
  | "garmin_fit_replay"
  | "garmin_influx_backfill"
  | "garmin_influx_live"
  | "replay"
  | "synthetic";
export type DedupeKey = string;
export type Sequence1 = number;
export type SourceRecordId = string | null;
export type HeartRateBpm = number | null;
export type RestingHrBpm = number | null;
export type HrvRmssdMs = number | null;
export type RespirationBrpm = number | null;
export type Spo2Pct = number | null;
export type ActivityLevel = number | null;
export type Start = string;
export type End = string;
export type TotalMinutes = number;
export type AwakeMinutes = number | null;
export type LightMinutes = number | null;
export type DeepMinutes = number | null;
export type RemMinutes = number | null;
export type EfficiencyPct = number | null;
export type Score1 = number | null;
export type Steps = number | null;
export type BodyBattery = number | null;
export type StressLevel = number | null;
export type TotalCalories = number | null;
export type DistanceM = number | null;
export type AccelerationMg = number | null;
export type MaxHrBpm = number | null;
export type MinHrBpm = number | null;
export type DistanceMeters = number | null;
export type BodyBatteryPct = number | null;
export type BodyBatteryCharged = number | null;
export type BodyBatteryDrained = number | null;
export type BodyBatteryAtWake = number | null;
export type StressAvg = number | null;
export type StressMax = number | null;
export type StressHighMin = number | null;
export type StressMediumMin = number | null;
export type StressLowMin = number | null;
export type ActiveCalories = number | null;
export type ActiveKcal = number | null;
export type ActiveSeconds = number | null;
export type HighlyActiveSeconds = number | null;
export type FloorsClimbed = number | null;
export type FloorsAscended = number | null;
export type ModerateIntensityMin = number | null;
export type VigorousIntensityMin = number | null;
export type Confidence1 = number;
export type UserId2 = string;
export type ComputedAt1 = string;
export type NObservations = number;
export type ShrinkageWeight = number;
export type Median = number;
export type Mad = number;
export type P10 = number;
export type P90 = number;
export type NDays = number;
export type RecoveryTauS = number | null;
export type TauFitRmse = number | null;
export type TauFitNSessions = number;
export type TauIqr = number[];
export type CvErrors = number[];
export type PriorLabel = string;
export type ModelVersion = string;
export type PulseHz = number | null;
export type BreathHz = number | null;
export type Fatigue = number;
export type Exertion = number;
export type RecoveryProgress = number;
export type Scenario = "rest" | "light" | "exercise";
export type Label = string;
export type Time = string;
export type Value = number;
export type Lower = number | null;
export type Upper = number | null;
export type Curve = CurvePoint[];
export type Assumption = string;
export type EventTime1 = string;
export type Confidence2 = number;
export type Contested = boolean;
export type Alternatives = {
  [k: string]: unknown;
}[];
export type LatencyMs = number;
export type Id = string;
export type IssuedAt = string;
export type HorizonS = number;
export type Curve1 = CurvePoint[];
export type Observed = CurvePoint[];
export type Rmse = number | null;
export type ModelVersion1 = string;
export type Assumption1 = string;
export type Date = string;
export type Timezone = string;
export type CalendarStatus = "connected" | "demo" | "unavailable";
export type Id1 = string;
export type Kind = "nap" | "workout";
export type Title = string;
export type Start1 = string;
export type End1 = string;
export type Intensity = string;
export type Reason = string;
export type Score2 = number;
export type Proposals = Proposal[];
export type Start2 = string;
export type End2 = string;
export type Title1 = string;
export type Busy = BusyInterval[];
export type Explanation = string;
export type IssuedAt1 = string;
export type Key = string;
export type Label1 = string;
export type Value1 = string;
export type Status = "good" | "watch" | "limited" | "unknown";
export type StateMetrics = HarnessMetric[];
export type ForecastSummary = HarnessMetric[];
export type Key1 = string;
export type Label2 = string;
export type Value2 = string;
export type Reason1 = string;
export type Policy = HarnessDecision[];
export type Evaluations = HarnessDecision[];
export type NextActions = string[];
export type Confidence3 = number;
export type Calendar = {
  [k: string]: unknown;
} | null;
export type RecentTrend = string[];
export type Facts = string[];
export type Answer = string;
export type Mode = "template" | "language_service" | "guard_fallback";
export type Grounded = boolean;
export type Notice = string | null;
export type Model = string | null;
export type Id2 = string;
export type Question = string;
export type Answer1 = string | null;
export type CreatedAt = string;
export type CompletedAt = string | null;
export type Mode1 = string;
export type Notice1 = string | null;
export type Model1 = string | null;
export type IssuedAt2 = string;
export type Timezone1 = string;
export type Curve2 = CurvePoint[];
export type Confidence4 = number;
export type Label3 = string;
export type Assumptions = string;

export interface BioTwinContracts {
  TwinState: TwinState;
  TwinFrame: TwinFrame;
  Baseline: Baseline;
  Readiness: Readiness;
  RecoveryPrediction: RecoveryPrediction;
  DailyPlan: DailyPlan;
  FitnessHarness: FitnessHarness;
  NarrationContext: NarrationContext;
  NarrationResponse: NarrationResponse;
  Conversation: Conversation;
  SimulationOverlay: SimulationOverlay;
  DayOutlook: DayOutlook;
}
export interface TwinState {
  energy_reserve_pct?: EnergyReservePct;
  schema_version?: SchemaVersion;
  sequence: Sequence;
  server_time: ServerTime;
  readiness: Readiness;
  latest: TwinFrame | null;
  baseline_summary: Baseline;
  drivers: AvatarDrivers;
  simulation?: SimulationOverlay | null;
  provenance_banner: Provenance;
  quality?: Quality;
  latency_ms?: LatencyMs;
  prediction?: RecoveryPrediction | null;
}
export interface Readiness {
  user_id: UserId;
  computed_at: ComputedAt;
  score?: Score;
  state: EnergyState;
  contributions: Contributions;
  confidence: Confidence;
  degraded_reason?: DegradedReason;
  sleep_debt_minutes?: SleepDebtMinutes;
  cuts?: Cuts;
}
export interface Contributions {
  [k: string]: number;
}
export interface TwinFrame {
  user_id: UserId1;
  event_time: EventTime;
  ingest_time?: IngestTime;
  provenance: Provenance;
  dedupe_key?: DedupeKey;
  sequence?: Sequence1;
  source_record_id?: SourceRecordId;
  heart_rate_bpm?: HeartRateBpm;
  resting_hr_bpm?: RestingHrBpm;
  hrv_rmssd_ms?: HrvRmssdMs;
  respiration_brpm?: RespirationBrpm;
  spo2_pct?: Spo2Pct;
  activity_level?: ActivityLevel;
  sleep?: SleepSummary | null;
  steps?: Steps;
  body_battery?: BodyBattery;
  stress_level?: StressLevel;
  total_calories?: TotalCalories;
  distance_m?: DistanceM;
  acceleration_mg?: AccelerationMg;
  max_hr_bpm?: MaxHrBpm;
  min_hr_bpm?: MinHrBpm;
  distance_meters?: DistanceMeters;
  body_battery_pct?: BodyBatteryPct;
  body_battery_charged?: BodyBatteryCharged;
  body_battery_drained?: BodyBatteryDrained;
  body_battery_at_wake?: BodyBatteryAtWake;
  stress_avg?: StressAvg;
  stress_max?: StressMax;
  stress_high_min?: StressHighMin;
  stress_medium_min?: StressMediumMin;
  stress_low_min?: StressLowMin;
  active_calories?: ActiveCalories;
  active_kcal?: ActiveKcal;
  active_seconds?: ActiveSeconds;
  highly_active_seconds?: HighlyActiveSeconds;
  floors_climbed?: FloorsClimbed;
  floors_ascended?: FloorsAscended;
  moderate_intensity_min?: ModerateIntensityMin;
  vigorous_intensity_min?: VigorousIntensityMin;
  confidence?: Confidence1;
}
export interface SleepSummary {
  start: Start;
  end: End;
  total_minutes: TotalMinutes;
  awake_minutes?: AwakeMinutes;
  light_minutes?: LightMinutes;
  deep_minutes?: DeepMinutes;
  rem_minutes?: RemMinutes;
  efficiency_pct?: EfficiencyPct;
  score?: Score1;
}
export interface Baseline {
  user_id: UserId2;
  computed_at: ComputedAt1;
  n_observations: NObservations;
  shrinkage_weight: ShrinkageWeight;
  resting_hr: RobustStat;
  hrv_rmssd: RobustStat;
  sleep_minutes: RobustStat;
  respiration: RobustStat;
  recovery_tau_s?: RecoveryTauS;
  tau_fit_rmse?: TauFitRmse;
  tau_fit_n_sessions?: TauFitNSessions;
  tau_iqr?: TauIqr;
  cv_errors?: CvErrors;
  prior_label?: PriorLabel;
  model_version?: ModelVersion;
}
export interface RobustStat {
  median: Median;
  mad: Mad;
  p10: P10;
  p90: P90;
  n_days?: NDays;
}
export interface AvatarDrivers {
  pulse_hz?: PulseHz;
  breath_hz?: BreathHz;
  fatigue: Fatigue;
  exertion: Exertion;
  recovery_progress: RecoveryProgress;
}
export interface SimulationOverlay {
  scenario: Scenario;
  label?: Label;
  drivers: AvatarDrivers;
  curve: Curve;
  assumption: Assumption;
}
export interface CurvePoint {
  time: Time;
  value: Value;
  lower?: Lower;
  upper?: Upper;
}
export interface Quality {
  [k: string]: MetricQuality;
}
export interface MetricQuality {
  provenance: Provenance;
  event_time: EventTime1;
  confidence: Confidence2;
  contested?: Contested;
  alternatives?: Alternatives;
}
export interface RecoveryPrediction {
  id: Id;
  issued_at: IssuedAt;
  horizon_s: HorizonS;
  curve: Curve1;
  observed?: Observed;
  rmse?: Rmse;
  model_version?: ModelVersion1;
  provenance: Provenance;
  assumption?: Assumption1;
}
export interface DailyPlan {
  date: Date;
  timezone: Timezone;
  calendar_status: CalendarStatus;
  proposals: Proposals;
  busy: Busy;
  explanation: Explanation;
}
export interface Proposal {
  id: Id1;
  kind: Kind;
  title: Title;
  start: Start1;
  end: End1;
  intensity: Intensity;
  reason: Reason;
  score: Score2;
  terms: Terms;
}
export interface Terms {
  [k: string]: number;
}
export interface BusyInterval {
  start: Start2;
  end: End2;
  title?: Title1;
}
export interface FitnessHarness {
  issued_at: IssuedAt1;
  state_metrics: StateMetrics;
  forecast_summary: ForecastSummary;
  policy: Policy;
  evaluations: Evaluations;
  next_actions: NextActions;
  confidence: Confidence3;
}
export interface HarnessMetric {
  key: Key;
  label: Label1;
  value: Value1;
  status?: Status;
}
export interface HarnessDecision {
  key: Key1;
  label: Label2;
  value: Value2;
  reason: Reason1;
}
export interface NarrationContext {
  calendar?: Calendar;
  readiness: Readiness;
  baseline_summary: Baseline;
  recent_trend?: RecentTrend;
  plan?: DailyPlan | null;
  prediction?: RecoveryPrediction | null;
  harness?: FitnessHarness | null;
  facts?: Facts;
  provenance?: Provenance | null;
  quality?: Quality1;
}
export interface Quality1 {
  [k: string]: MetricQuality;
}
export interface NarrationResponse {
  answer: Answer;
  mode: Mode;
  grounded?: Grounded;
  notice?: Notice;
  model?: Model;
}
export interface Conversation {
  id: Id2;
  question: Question;
  answer?: Answer1;
  created_at: CreatedAt;
  completed_at?: CompletedAt;
  mode: Mode1;
  notice?: Notice1;
  model?: Model1;
}
export interface DayOutlook {
  issued_at: IssuedAt2;
  timezone: Timezone1;
  curve: Curve2;
  confidence: Confidence4;
  label?: Label3;
  assumptions: Assumptions;
}
