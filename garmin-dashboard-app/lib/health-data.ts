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

export async function getHeartRateHistory(hours: number): Promise<SeriesPoint[]> {
  const series = await influxQuery(
    `SELECT "HeartRate" FROM "HeartRateIntraday" WHERE time > now() - ${hours}h ORDER BY time ASC`,
  );
  return rows(series).map((r) => ({ t: r.time as string, v: r.HeartRate as number }));
}

export async function getStepsHistory(days: number): Promise<SeriesPoint[]> {
  const series = await influxQuery(
    `SELECT "totalSteps" FROM "DailyStats" WHERE time > now() - ${days}d ORDER BY time ASC`,
  );
  return rows(series).map((r) => ({ t: r.time as string, v: r.totalSteps as number }));
}

export async function getStressHistory(hours: number): Promise<SeriesPoint[]> {
  const series = await influxQuery(
    `SELECT "stressLevel" FROM "StressIntraday" WHERE time > now() - ${hours}h AND "stressLevel" >= 0 ORDER BY time ASC`,
  );
  return rows(series).map((r) => ({ t: r.time as string, v: r.stressLevel as number }));
}

export async function getBodyBatteryHistory(hours: number): Promise<SeriesPoint[]> {
  const series = await influxQuery(
    `SELECT "BodyBatteryLevel" FROM "BodyBatteryIntraday" WHERE time > now() - ${hours}h ORDER BY time ASC`,
  );
  return rows(series).map((r) => ({ t: r.time as string, v: r.BodyBatteryLevel as number }));
}
