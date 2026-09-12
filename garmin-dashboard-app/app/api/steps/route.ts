import { getStepsHistory } from "@/lib/health-data";

export async function GET(request: Request) {
  const days = Number(new URL(request.url).searchParams.get("days") ?? "7");
  return Response.json({ points: await getStepsHistory(days) });
}
