import { influxQuery, rows } from "./influx";

export type Summary = {
  latestHr: number | null;
  steps: number | null;
  restingHr: number | null;
  calories: number | null;
  sleepSeconds: number | null;
  sleepScore: number | null;
  device: string;
};

export type SeriesPoint = { t: string; v: number };

export async function getSummary(): Promise<Summary> {
  const [hrSeries, dailySeries, sleepSeries, deviceSeries] = await Promise.all([
    influxQuery(`SELECT last("HeartRate") FROM "HeartRateIntraday"`),
    influxQuery(
      `SELECT last("totalSteps") AS steps, last("restingHeartRate") AS resting, last("activeKilocalories") AS calories FROM "DailyStats"`,
    ),
    influxQuery(
      `SELECT last("sleepTimeSeconds") AS seconds, last("sleepScore") AS score FROM "SleepSummary"`,
    ),
    // "Device" collides with a tag of the same name on this measurement
    // (an upstream ingestion quirk) and silently returns nothing when
    // queried directly -- "Device_Name" is the same value with no collision.
    influxQuery(`SELECT last("Device_Name") AS device FROM "DeviceSync"`),
  ]);

  const hr = rows(hrSeries)[0];
  const daily = rows(dailySeries)[0];
  const sleep = rows(sleepSeries)[0];
  const device = rows(deviceSeries)[0];

  return {
    latestHr: (hr?.last as number) ?? null,
    steps: (daily?.steps as number) ?? null,
    restingHr: (daily?.resting as number) ?? null,
    calories: (daily?.calories as number) ?? null,
    sleepSeconds: (sleep?.seconds as number) ?? null,
    sleepScore: (sleep?.score as number) ?? null,
    device: (device?.device as string) ?? "your watch",
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
