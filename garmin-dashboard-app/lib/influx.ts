// Thin fetch-based InfluxDB 1.x client. No SDK needed -- InfluxQL over HTTP
// is just a GET with a query string, same as the raw `curl` calls used to
// diagnose the Grafana refresh bug this app exists to route around.

const INFLUX_HOST = process.env.INFLUX_HOST ?? "localhost";
const INFLUX_PORT = process.env.INFLUX_PORT ?? "8086";
const INFLUX_DATABASE = process.env.INFLUX_DATABASE ?? "GarminStats";

export type InfluxSeries = {
  name: string;
  columns: string[];
  values: (string | number | null)[][];
};

export type InfluxResult = {
  results: { series?: InfluxSeries[]; error?: string }[];
};

export async function influxQuery(q: string): Promise<InfluxSeries[]> {
  const url = new URL(`http://${INFLUX_HOST}:${INFLUX_PORT}/query`);
  url.searchParams.set("db", INFLUX_DATABASE);
  url.searchParams.set("q", q);

  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`InfluxDB query failed (${res.status}): ${await res.text()}`);
  }
  const json = (await res.json()) as InfluxResult;
  const result = json.results?.[0];
  if (result?.error) throw new Error(`InfluxDB error: ${result.error}`);
  return result?.series ?? [];
}

/** Row objects keyed by column name, instead of Influx's parallel arrays. */
export function rows(series: InfluxSeries[]): Record<string, string | number | null>[] {
  const s = series[0];
  if (!s) return [];
  return s.values.map((row) =>
    Object.fromEntries(s.columns.map((col, i) => [col, row[i]])),
  );
}
