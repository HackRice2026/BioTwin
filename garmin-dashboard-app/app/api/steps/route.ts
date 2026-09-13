import { getStepsHistory, type Range } from "@/lib/health-data";

export async function GET(request: Request) {
  const range = new URL(request.url).searchParams.get("range");
  return Response.json({
    points: await getStepsHistory(range === "week" ? "week" : ("day" as Range)),
  });
}
