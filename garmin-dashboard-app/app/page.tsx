import {
  BatteryMedium,
  Bed,
  Droplet,
  Flame,
  Footprints,
  Gauge,
  HeartPulse,
  Mountain,
  Route,
  Scale,
  Sparkles,
  Waves,
  Wind,
} from "lucide-react";
import type { ReactNode } from "react";
import Link from "next/link";
import {
  getHeartRateHistory,
  getStepsHistory,
  getSummary,
} from "@/lib/health-data";
import { LiveHeartCard } from "@/components/health/live-heart-card";
import { MetricCard } from "@/components/health/metric-card";
import { Carousel, CarouselItem } from "@/components/health/carousel";
import { InsightCard } from "@/components/health/insight-card";
import { SleepStagesBar } from "@/components/health/sleep-stages-bar";

export const dynamic = "force-dynamic";

function formatDuration(totalSeconds: number | null): string {
  if (totalSeconds == null) return "--";
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.round((totalSeconds % 3600) / 60);
  return `${h}h ${m}m`;
}

function formatDistance(meters: number | null): string {
  if (meters == null) return "--";
  return (meters / 1000).toFixed(2);
}

function formatWeight(grams: number | null): string {
  if (grams == null) return "--";
  return (grams / 1000).toFixed(1);
}

function stressLabel(level: number | null): string {
  if (level == null || level < 0) return "--";
  if (level < 25) return "Resting";
  if (level < 50) return "Low";
  if (level < 75) return "Medium";
  return "High";
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-2">
      <h2 className="px-1 text-xs font-semibold uppercase tracking-wider text-muted-foreground">
        {title}
      </h2>
      {children}
    </section>
  );
}

export default async function Home() {
  const [summary, hrPoints, stepsPoints] = await Promise.all([
    getSummary(),
    getHeartRateHistory("day"),
    getStepsHistory("week"),
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

      <InsightCard body={insight} />

      <Section title="Heart">
        <Carousel>
          <CarouselItem>
            <MetricCard
              icon={HeartPulse}
              color="coral"
              title="Heart rate (24h)"
              value={summary.latestHr ?? "--"}
              unit="bpm"
              points={hrPoints}
              href="/metric/heart-rate"
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={HeartPulse}
              color="coral"
              title="Resting"
              value={summary.restingHr ?? "--"}
              unit="bpm"
              href="/metric/heart-rate"
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Gauge}
              color="coral"
              title="Range today"
              value={
                summary.minHr != null && summary.maxHr != null
                  ? `${summary.minHr}–${summary.maxHr}`
                  : "--"
              }
              unit="bpm"
              href="/metric/heart-rate"
            />
          </CarouselItem>
        </Carousel>
      </Section>

      <Section title="Activity">
        <Carousel>
          <CarouselItem>
            <MetricCard
              icon={Footprints}
              color="amber"
              title="Steps today"
              value={summary.steps?.toLocaleString() ?? "--"}
              points={stepsPoints}
              href="/metric/activity"
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Route}
              color="amber"
              title="Distance"
              value={formatDistance(summary.distanceMeters)}
              unit="km"
              href="/metric/activity"
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Mountain}
              color="amber"
              title="Floors climbed"
              value={summary.floorsAscended ?? "--"}
              href="/metric/activity"
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Flame}
              color="amber"
              title="Active calories"
              value={summary.calories?.toLocaleString() ?? "--"}
              unit="kcal"
              href="/metric/activity"
            />
          </CarouselItem>
        </Carousel>
      </Section>

      <Section title="Body">
        <Carousel>
          <CarouselItem>
            <MetricCard
              icon={BatteryMedium}
              color="violet"
              title="Body battery"
              value={summary.bodyBattery ?? "--"}
              unit="/ 100"
              href="/metric/body-battery"
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Waves}
              color="violet"
              title="Stress"
              value={stressLabel(summary.stressLevel)}
              unit={summary.stressLevel != null && summary.stressLevel >= 0 ? `(${summary.stressLevel})` : undefined}
              href="/metric/stress"
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Sparkles}
              color="violet"
              title="Fitness age"
              value={summary.fitnessAge ?? "--"}
            />
          </CarouselItem>
          <CarouselItem>
            <MetricCard
              icon={Scale}
              color="violet"
              title="Weight"
              value={formatWeight(summary.weightGrams)}
              unit="kg"
            />
          </CarouselItem>
        </Carousel>
      </Section>

      <Section title="Sleep">
        <div className="grid gap-3 lg:grid-cols-[repeat(3,minmax(0,1fr))_2fr]">
          <MetricCard
            icon={Bed}
            color="teal"
            title="Duration"
            value={formatDuration(summary.sleepSeconds)}
            href="/metric/sleep"
          />
          <MetricCard
            icon={Droplet}
            color="teal"
            title="Blood oxygen"
            value={summary.sleepSpO2 ?? "--"}
            unit="%"
            href="/metric/sleep"
          />
          <MetricCard
            icon={Wind}
            color="teal"
            title="Breathing rate"
            value={summary.breathingRate ?? "--"}
            unit="brpm"
            href="/metric/sleep"
          />
          <Link
            href="/metric/sleep"
            className="flex flex-col justify-center gap-2 rounded-3xl border border-border bg-card p-5 hover:opacity-90"
          >
            <span className="text-[11px] uppercase tracking-wider text-muted-foreground">
              Sleep stages
            </span>
            <SleepStagesBar
              deep={summary.deepSleepSeconds}
              light={summary.lightSleepSeconds}
              rem={summary.remSleepSeconds}
              awake={summary.awakeSleepSeconds}
            />
          </Link>
        </div>
      </Section>

      <footer className="mt-auto pt-4 text-center text-xs text-muted-foreground">
        Synced from {summary.device}
      </footer>
    </main>
  );
}
