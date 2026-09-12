import { getHeartRateHistory, type Range } from "@/lib/health-data";

export async function GET(request: Request) {
  const range = new URL(request.url).searchParams.get("range");
  return Response.json({
    points: await getHeartRateHistory(range === "week" ? "week" : ("day" as Range)),
  });
}
