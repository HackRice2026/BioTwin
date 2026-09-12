import { Activity, Bed, Flame, HeartPulse } from "lucide-react";
import { getHeartRateHistory, getStepsHistory, getSummary } from "@/lib/health-data";
import { LiveHeartCard } from "@/components/health/live-heart-card";
import { MetricCard } from "@/components/health/metric-card";
import { Carousel, CarouselItem } from "@/components/health/carousel";
import { InsightCard } from "@/components/health/insight-card";

export const dynamic = "force-dynamic";

function formatSleep(totalSeconds: number | null): string {
  if (totalSeconds == null) return "--";
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.round((totalSeconds % 3600) / 60);
  return `${h}h ${m}m`;
}

export default async function Home() {
  const [summary, hrPoints, stepsPoints] = await Promise.all([
    getSummary(),
    getHeartRateHistory(3),
    getStepsHistory(7),
  ]);

  const insight =
    summary.restingHr != null
      ? `Your resting heart rate today is ${summary.restingHr} bpm${
          summary.steps != null
            ? `, with ${summary.steps.toLocaleString()} steps logged so far.`
            : "."
        }`
      : "Once your watch syncs today's data, a summary will show up here.";

  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-6 px-4 pb-10 pt-8 sm:max-w-2xl lg:max-w-5xl lg:pt-12">
      <header>
        <p className="text-sm text-muted-foreground">Good to see you</p>
        <h1 className="font-display text-3xl font-medium text-foreground">
          Today&rsquo;s health
        </h1>
      </header>

      <LiveHeartCard fallbackBpm={summary.latestHr} />

      <section className="flex flex-col gap-2">
        <h2 className="px-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          Overview
        </h2>
        <Carousel>
          <CarouselItem>
            <MetricCard
              icon={Activity}
              color="amber"
              title="Steps today"
              value={summary.steps?.toLocaleString() ?? "--"}
              points={stepsPoints}
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={HeartPulse}
              color="coral"
              title="Heart rate (3h)"
              value={summary.latestHr ?? "--"}
              unit="bpm"
              points={hrPoints}
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Bed}
              color="violet"
              title="Sleep last night"
              value={formatSleep(summary.sleepSeconds)}
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Flame}
              color="teal"
              title="Active calories"
              value={summary.calories?.toLocaleString() ?? "--"}
              unit="kcal"
            />
          </CarouselItem>
        </Carousel>
      </section>

      <InsightCard body={insight} />

      <footer className="mt-auto pt-4 text-center text-xs text-muted-foreground">
        Synced from {summary.device}
      </footer>
    </main>
  );
}
