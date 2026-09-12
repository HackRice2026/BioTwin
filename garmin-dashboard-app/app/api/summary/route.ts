import { getSummary } from "@/lib/health-data";

export async function GET() {
  return Response.json(await getSummary());
}
