import { getHeartRateHistory } from "@/lib/health-data";

export async function GET(request: Request) {
  const hours = Number(new URL(request.url).searchParams.get("hours") ?? "3");
  return Response.json({ points: await getHeartRateHistory(hours) });
}
