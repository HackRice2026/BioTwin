import { influxQuery, rows } from "./influx";

export type Summary = {
  device: string;
  // heart
  latestHr: number | null;
  restingHr: number | null;
  maxHr: number | null;
  minHr: number | null;
  // activity
  steps: number | null;
  distanceMeters: number | null;
  floorsAscended: number | null;
  calories: number | null;
  // body
  bodyBattery: number | null;
  stressLevel: number | null;
  fitnessAge: number | null;
  weightGrams: number | null;
  // sleep
  sleepSeconds: number | null;
  sleepScore: number | null;
  sleepSpO2: number | null;
  breathingRate: number | null;
  deepSleepSeconds: number | null;
  lightSleepSeconds: number | null;
  remSleepSeconds: number | null;
  awakeSleepSeconds: number | null;
};

export type SeriesPoint = { t: string; v: number };
/** "day" and "week" only -- real data only goes back ~7 days right now, so a
 * "month" option would mostly render empty space. Add it once there's
 * actually a month of history; every query below already takes an arbitrary
 * day count, so it's a one-line change, not a redesign. */
export type Range = "day" | "week";

export async function getSummary(): Promise<Summary> {
  const [
    hrSeries,
    dailySeries,
    sleepSeries,
    deviceSeries,
    batterySeries,
    stressSeries,
    fitnessSeries,
    weightSeries,
  ] = await Promise.all([
    influxQuery(`SELECT last("HeartRate") FROM "HeartRateIntraday"`),
    influxQuery(
      `SELECT last("totalSteps") AS steps, last("restingHeartRate") AS resting, last("maxHeartRate") AS maxHr, last("minHeartRate") AS minHr, last("activeKilocalories") AS calories, last("totalDistanceMeters") AS distance, last("floorsAscended") AS floors FROM "DailyStats"`,
    ),
    influxQuery(
      `SELECT last("sleepTimeSeconds") AS seconds, last("sleepScore") AS score, last("averageSpO2Value") AS spo2, last("averageRespirationValue") AS breathing, last("deepSleepSeconds") AS deep, last("lightSleepSeconds") AS light, last("remSleepSeconds") AS rem, last("awakeSleepSeconds") AS awake FROM "SleepSummary"`,
    ),
    // "Device" collides with a tag of the same name on this measurement
    // (an upstream ingestion quirk) and silently returns nothing when
    // queried directly -- "Device_Name" is the same value with no collision.
    influxQuery(`SELECT last("Device_Name") AS device FROM "DeviceSync"`),
    influxQuery(`SELECT last("BodyBatteryLevel") AS level FROM "BodyBatteryIntraday"`),
    influxQuery(`SELECT last("stressLevel") AS level FROM "StressIntraday"`),
    influxQuery(`SELECT last("fitnessAge") AS age FROM "FitnessAge"`),
    influxQuery(`SELECT last("weight") AS grams FROM "BodyComposition"`),
  ]);

  const hr = rows(hrSeries)[0];
  const daily = rows(dailySeries)[0];
  const sleep = rows(sleepSeries)[0];
  const device = rows(deviceSeries)[0];
  const battery = rows(batterySeries)[0];
  const stress = rows(stressSeries)[0];
  const fitness = rows(fitnessSeries)[0];
  const weight = rows(weightSeries)[0];

  return {
    device: (device?.device as string) ?? "your watch",
    latestHr: (hr?.last as number) ?? null,
    restingHr: (daily?.resting as number) ?? null,
    maxHr: (daily?.maxHr as number) ?? null,
    minHr: (daily?.minHr as number) ?? null,
    steps: (daily?.steps as number) ?? null,
    distanceMeters: (daily?.distance as number) ?? null,
    floorsAscended: (daily?.floors as number) ?? null,
    calories: (daily?.calories as number) ?? null,
    bodyBattery: (battery?.level as number) ?? null,
    stressLevel: (stress?.level as number) ?? null,
    fitnessAge: (fitness?.age as number) ?? null,
    weightGrams: (weight?.grams as number) ?? null,
    sleepSeconds: (sleep?.seconds as number) ?? null,
    sleepScore: (sleep?.score as number) ?? null,
    sleepSpO2: (sleep?.spo2 as number) ?? null,
    breathingRate: (sleep?.breathing as number) ?? null,
    deepSleepSeconds: (sleep?.deep as number) ?? null,
    lightSleepSeconds: (sleep?.light as number) ?? null,
    remSleepSeconds: (sleep?.rem as number) ?? null,
    awakeSleepSeconds: (sleep?.awake as number) ?? null,
  };
}

function toPoints(series: Awaited<ReturnType<typeof influxQuery>>, field: string): SeriesPoint[] {
  // InfluxDB's mean() (used for the "week" range's hourly aggregation)
  // returns floats -- round here, once, so every consumer (chart tooltip,
  // summary stat tiles) gets clean numbers instead of each needing to
  // remember to round separately.
  return rows(series)
    .map((r) => ({ t: r.time as string, v: r[field] as number }))
    .filter((p) => p.v != null)
    .map((p) => ({ ...p, v: Math.round(p.v) }));
}

export async function getHeartRateHistory(range: Range): Promise<SeriesPoint[]> {
  const q =
    range === "day"
      ? `SELECT "HeartRate" FROM "HeartRateIntraday" WHERE time > now() - 24h ORDER BY time ASC`
      : `SELECT mean("HeartRate") AS "HeartRate" FROM "HeartRateIntraday" WHERE time > now() - 7d GROUP BY time(1h) fill(none)`;
  return toPoints(await influxQuery(q), "HeartRate");
}

export async function getStepsHistory(range: Range): Promise<SeriesPoint[]> {
  const q =
    range === "day"
      ? `SELECT sum("StepsCount") AS "totalSteps" FROM "StepsIntraday" WHERE time > now() - 24h GROUP BY time(30m) fill(0)`
      : `SELECT "totalSteps" FROM "DailyStats" WHERE time > now() - 7d ORDER BY time ASC`;
  return toPoints(await influxQuery(q), "totalSteps");
}

export async function getStressHistory(range: Range): Promise<SeriesPoint[]> {
  const q =
    range === "day"
      ? `SELECT "stressLevel" FROM "StressIntraday" WHERE time > now() - 24h AND "stressLevel" >= 0 ORDER BY time ASC`
      : `SELECT mean("stressLevel") AS "stressLevel" FROM "StressIntraday" WHERE time > now() - 7d AND "stressLevel" >= 0 GROUP BY time(1h) fill(none)`;
  return toPoints(await influxQuery(q), "stressLevel");
}

export async function getBodyBatteryHistory(range: Range): Promise<SeriesPoint[]> {
  const q =
    range === "day"
      ? `SELECT "BodyBatteryLevel" FROM "BodyBatteryIntraday" WHERE time > now() - 24h ORDER BY time ASC`
      : `SELECT mean("BodyBatteryLevel") AS "BodyBatteryLevel" FROM "BodyBatteryIntraday" WHERE time > now() - 7d GROUP BY time(2h) fill(none)`;
  return toPoints(await influxQuery(q), "BodyBatteryLevel");
}

export async function getDistanceHistory(range: Range): Promise<SeriesPoint[]> {
  const q =
    range === "day"
      ? `SELECT "totalDistanceMeters" FROM "DailyStats" WHERE time > now() - 24h ORDER BY time ASC`
      : `SELECT "totalDistanceMeters" FROM "DailyStats" WHERE time > now() - 7d ORDER BY time ASC`;
  return toPoints(await influxQuery(q), "totalDistanceMeters");
}

export type NightSummary = {
  t: string;
  sleepSeconds: number;
  sleepScore: number | null;
  deep: number;
  light: number;
  rem: number;
  awake: number;
  spo2: number | null;
};

export async function getSleepNights(nights: number): Promise<NightSummary[]> {
  const series = await influxQuery(
    `SELECT "sleepTimeSeconds", "sleepScore", "deepSleepSeconds", "lightSleepSeconds", "remSleepSeconds", "awakeSleepSeconds", "averageSpO2Value" FROM "SleepSummary" WHERE time > now() - ${nights}d ORDER BY time ASC`,
  );
  return rows(series).map((r) => ({
    t: r.time as string,
    sleepSeconds: (r.sleepTimeSeconds as number) ?? 0,
    sleepScore: (r.sleepScore as number) ?? null,
    deep: (r.deepSleepSeconds as number) ?? 0,
    light: (r.lightSleepSeconds as number) ?? 0,
    rem: (r.remSleepSeconds as number) ?? 0,
    awake: (r.awakeSleepSeconds as number) ?? 0,
    spo2: (r.averageSpO2Value as number) ?? null,
  }));
}
