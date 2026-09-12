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
import {
  getBodyBatteryHistory,
  getHeartRateHistory,
  getStepsHistory,
  getStressHistory,
  getSummary,
  type Range,
} from "@/lib/health-data";
import { getProfile } from "@/lib/profile";
import { LiveHeartCard } from "@/components/health/live-heart-card";
import { ChartCard } from "@/components/health/chart-card";
import { MiniTile } from "@/components/health/mini-tile";
import { InsightCard } from "@/components/health/insight-card";
import { SleepStagesBar } from "@/components/health/sleep-stages-bar";
import { RangeTabs } from "@/components/health/range-tabs";
import { ProfileAvatarLink } from "@/components/profile/profile-avatar-link";

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

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ range?: string }>;
}) {
  const range: Range = (await searchParams).range === "week" ? "week" : "day";
  const timeFormat = range === "day" ? "clock" : "day-time";

  const [summary, hrPoints, stepsPoints, batteryPoints, stressPoints, profile] = await Promise.all([
    getSummary(),
    getHeartRateHistory(range),
    getStepsHistory(range),
    getBodyBatteryHistory(range),
    getStressHistory(range),
    getProfile(),
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
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col gap-5 px-4 pb-10 pt-6 sm:max-w-3xl lg:max-w-6xl lg:pt-10">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <p className="text-sm text-muted-foreground">
            Good to see you{profile.name ? `, ${profile.name}` : ""}
          </p>
          <h1 className="font-display text-3xl font-medium text-foreground">
            Today&rsquo;s health
          </h1>
          {profile.aim && (
            <p className="mt-1 text-sm text-amber">
              <span aria-hidden>🎯</span> {profile.aim}
            </p>
          )}
          {profile.motivation && (
            <p className="mt-0.5 text-sm italic text-muted-foreground">
              &ldquo;{profile.motivation}&rdquo;
            </p>
          )}
        </div>
        <div className="flex items-center gap-3">
          <RangeTabs basePath="/" current={range} />
          <ProfileAvatarLink photoDataUrl={profile.photoDataUrl} />
        </div>
      </div>

      <LiveHeartCard fallbackBpm={summary.latestHr} />

      {/* Real charts, inline, all driven by the same range toggle above --
          this is the actual pattern-reading surface, not a teaser for a tap. */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <ChartCard
          icon={HeartPulse}
          color="coral"
          title="Heart rate"
          current={summary.latestHr ?? "--"}
          unit="bpm"
          points={hrPoints}
          href={`/metric/heart-rate?range=${range}`}
          timeFormat={timeFormat}
        />
        <ChartCard
          icon={Footprints}
          color="amber"
          title="Steps"
          current={summary.steps?.toLocaleString() ?? "--"}
          points={stepsPoints}
          href={`/metric/activity?range=${range}`}
          timeFormat={range === "day" ? "clock" : "day"}
        />
        <ChartCard
          icon={BatteryMedium}
          color="violet"
          title="Body battery"
          current={summary.bodyBattery ?? "--"}
          unit="/100"
          points={batteryPoints}
          href={`/metric/body-battery?range=${range}`}
          timeFormat={timeFormat}
        />
        <ChartCard
          icon={Waves}
          color="violet"
          title="Stress"
          current={stressLabel(summary.stressLevel)}
          points={stressPoints}
          href={`/metric/stress?range=${range}`}
          timeFormat={timeFormat}
        />
      </div>

      {/* Single-snapshot metrics -- dense grid, no chart to fake, no tap
          required to just read the number. */}
      <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3 lg:grid-cols-6">
        <MiniTile icon={HeartPulse} color="coral" label="Resting HR" value={summary.restingHr ?? "--"} unit="bpm" href={`/metric/heart-rate?range=${range}`} />
        <MiniTile
          icon={Gauge}
          color="coral"
          label="HR range"
          value={summary.minHr != null && summary.maxHr != null ? `${summary.minHr}–${summary.maxHr}` : "--"}
          href={`/metric/heart-rate?range=${range}`}
        />
        <MiniTile icon={Route} color="amber" label="Distance" value={formatDistance(summary.distanceMeters)} unit="km" href={`/metric/activity?range=${range}`} />
        <MiniTile icon={Mountain} color="amber" label="Floors" value={summary.floorsAscended ?? "--"} href={`/metric/activity?range=${range}`} />
        <MiniTile icon={Flame} color="amber" label="Calories" value={summary.calories?.toLocaleString() ?? "--"} unit="kcal" href={`/metric/activity?range=${range}`} />
        <MiniTile icon={Sparkles} color="violet" label="Fitness age" value={summary.fitnessAge ?? "--"} />
        <MiniTile icon={Scale} color="violet" label="Weight" value={formatWeight(summary.weightGrams)} unit="kg" />
        <MiniTile icon={Bed} color="teal" label="Sleep" value={formatDuration(summary.sleepSeconds)} href="/metric/sleep" />
        <MiniTile icon={Droplet} color="teal" label="Blood oxygen" value={summary.sleepSpO2 ?? "--"} unit="%" href="/metric/sleep" />
        <MiniTile icon={Wind} color="teal" label="Breathing" value={summary.breathingRate ?? "--"} unit="brpm" href="/metric/sleep" />
      </div>

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-3">
        <div className="rounded-2xl border border-border bg-card p-4 lg:col-span-2">
          <span className="mb-2 block text-[11px] uppercase tracking-wider text-muted-foreground">
            Last night&rsquo;s sleep stages
          </span>
          <SleepStagesBar
            deep={summary.deepSleepSeconds}
            light={summary.lightSleepSeconds}
            rem={summary.remSleepSeconds}
            awake={summary.awakeSleepSeconds}
          />
        </div>
        <InsightCard body={insight} />
      </div>

      <footer className="pt-2 text-center text-xs text-muted-foreground">
        Synced from {summary.device}
      </footer>
    </main>
  );
}
