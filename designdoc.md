# Design Doc — Health Dashboard Theme

**Status:** design system defined, color-validated, and implemented as a working Next.js app at `BioTwin/garmin-dashboard-app/`. See the bottom of this doc for how to run it and what's built vs. still open.

## 1. Core theme: "Warm Editorial Minimal"

Editorial magazine typography (serif headers) combined with soft, low-contrast UI chrome (rounded cards, thin borders, pastel-tinted icon containers) — a warm, human-centric alternative to the clinical-blue look most health dashboards default to. Direct response to the current Grafana dashboard being confusing for a normal user: this system leads with one hero metric, tucks everything else one tap away, and never presents an undifferentiated wall of panels.

Inspiration pulled from the reference screenshots (patterns only, not their literal colors):
- Ring/streak indicators + horizontally scrollable metric-category cards ("Activity / Body / Heart")
- Sparkline-with-floating-tooltip cards (dark callout bubble pinned to a point on the line)
- Pill-shaped segmented time-range controls (Week / Month / Quarter / Year)
- Large hero figure + muted micro-label pairing (`65.8 Kg` over `Current Wt`)
- Soft pastel-tinted circular icon containers (dumbbell / heart / lightning bolt each in their own tint)
- A closing "Insight" callout box with AI-generated commentary — this maps to the planned third panel, see §8

## 2. Color system

Every hex below was run through the same computable checks this team already uses for the Garmin dashboards (`validate_palette.js` — lightness band, chroma floor, CVD separation, normal-vision floor, contrast vs. surface). Two of the four accent hues you specified didn't clear the checks as given; validated replacements are marked **(adjusted)**. Use the adjusted values for anything that has to read as a distinct color (chart lines, icon fills, active-state rings) — the original softer hex values are still fine as the **pastel fill/tint**, since those sit behind text and never need to carry identity alone.

### Neutrals

| Role | Hex | Usage |
|---|---|---|
| Background canvas | `#FDFCF9` → `#F9F8F3` | page background |
| Surface (cards, pills) | `#F6F4EE` | elevated containers |
| Primary ink | `#1C1B1F` – `#2D2C2A` | headers, hero figures, active states — **13–17:1 contrast** on both surfaces above, verified |
| Secondary/muted ink | `#6B6A66` | micro-labels, axis text, secondary copy — **5.3:1** on cream, clears AA |
| Border (hairline) | `rgba(28,27,31,0.08)` | card outlines — thin, low-opacity, never a heavy shadow |

### Accent colors (validated categorical set)

| Role | Mark color (validated) | Pastel fill/tint | Metric family |
|---|---|---|---|
| Primary (trends, streak rings) | `#C96A1E` **(adjusted from #D97724)** | `#F7E3CE` | primary indicators, key trend lines |
| Muted coral | `#DD5A49` **(adjusted from #E86C5D)** | `#FCEAE8` | heart rate, active weight tracking |
| Soft violet | `#9A63DE` **(adjusted from #A073E5)** | `#ECE3F8` | muscle mass, body composition |
| Teal / mint | `#008C82` **(adjusted from #46A29F)** | `#E8F5F5` | secondary weight averages |

Validator result on this exact order, against the `#F9F8F3` surface: **all five checks pass** — lightness band, chroma floor, adjacent CVD separation (worst pair ΔE 9.0), normal-vision floor (worst pair ΔE 24.4), and contrast (all ≥ 3:1). Keep this order if a fifth category ever gets added — re-run the validator rather than picking a hue by eye.

**Two hard rules that came straight out of the validator run, don't relitigate them per-component:**
1. These four mark colors are for **fills, icon glyphs, chart lines, and ring progress** — never for the actual data-value text sitting next to them. The hero figure and its label always stay in ink/muted-ink, per `marks-and-anatomy.md`'s "text never wears the data color" rule. This is also why the originally-specified hex values work fine as *pastel backgrounds* (a wash behind an icon has no contrast-vs-text requirement) even though they don't clear the mark-contrast floor.
2. A **single-metric chart** (one line, one card) can use any one of these four freely. The moment two of them appear **adjacent** in the same view (e.g., two sparklines side by side, or a stacked/legend comparison), keep them in the table's row order — that's the order the CVD check passed on.

### Status (reserved, not decorative)

Reuse the same status palette already validated for the Garmin Grafana dashboards rather than inventing a second one:

| Role | Hex |
|---|---|
| Good | `#0ca30c` |
| Warning | `#fab219` |
| Serious | `#ec835a` |
| Critical | `#d03b3b` |

Always paired with an icon + label, never color alone (e.g., a connection dot is fine since it's never shown two-states-at-once next to itself — see the live-heart-rate page for the working example of this pattern).

## 3. Typography

- **Display / section headers:** an editorial serif — Playfair Display or Instrument Serif. Large section titles only ("Advanced body weight monitoring system" style headers). Never on data figures.
- **Body, UI, data figures:** Inter or SF Pro (system sans). Hero figures and stat values use the font's **default proportional figures**, not tabular — `tabular-nums` is reserved for literal columns (a table, aligned axis ticks), per the same rule already applied to the Garmin live-HR page.
- **Micro-labels:** sans, secondary ink, small caps or letter-spaced uppercase (matches the reference screenshots' `Current Wt` / `Avg Wt` treatment).

## 4. Spacing & shape

- Corner radius: **16–24px** on cards, pill controls fully rounded (999px).
- Borders: 1px hairline at the `rgba(28,27,31,0.08)` token — no drop shadows as the primary separation mechanism; shadow only as a very subtle lift on the one "active/expanded" card at a time.
- Card padding: generous (20–24px) — the reference screens are never cramped.

## 5. Component patterns

- **Pill segmented control** (Week/Month/Quarter/Year): rounded-full track, active segment gets primary-ink background + white/cream text, inactive segments transparent with muted-ink text. Thumb-reach placement (top of a mobile view, not buried).
- **Soft-tinted icon container**: a circle (40–48px) in a metric's pastel fill color, glyph in that metric's mark color. One per metric-category card.
- **Stat tile**: micro-label (muted ink, uppercase) → hero value (ink, semibold, proportional figures) → optional small delta/sparkline underneath in the metric's mark color.
- **Sparkline + floating tooltip**: thin (2px) line, ~10% opacity area fill under it (matches the Garmin live-HR chart already built), a small dark pill tooltip pinned above the hovered/selected point showing the exact value.
- **Horizontal swipe carousel**: for the top-level metric-category cards (Activity / Body / Heart) on mobile — conserves vertical space, matches the reference screens exactly.
- **Ring / streak indicator**: circular progress, primary-ink track background, mark-color fill, center hero number.
- **Insight callout box**: soft gradient-bordered card, sparkle icon + "Insight" label header, ink body text. This is the slot for the planned AI-commentary panel (§8) — build the static version now, wire up the model later.

## 6. Icon system

**shadcn/ui doesn't ship its own icon set — it's built to pair with `lucide-react` by convention**, so "shadcn icons" and "Lucide" are the same recommendation here. Use `lucide-react` as the default. Good free/minimal fallbacks if a specific glyph is missing from Lucide:

| Library | License | Notes |
|---|---|---|
| **lucide-react** (primary) | ISC (free) | shadcn/ui's de facto default; huge coverage, consistent 2px stroke, tree-shakeable |
| Phosphor Icons | MIT | multiple weights (thin/light/regular/bold) if a warmer, less geometric line fits the editorial feel better |
| Tabler Icons | MIT | very large set, similar stroke weight to Lucide, good for niche health/fitness glyphs |
| Radix Icons | MIT | smaller set, very clean, good for UI chrome (chevrons, close, dots) rather than data glyphs |
| Heroicons | MIT | Tailwind's own; outline + solid variants |

Stick to one library's stroke weight throughout a single screen — mixing Lucide + Phosphor glyphs in the same card reads as inconsistent even though both are "minimal line icons."

## 7. Information hierarchy (the actual fix for "Grafana is confusing")

1. **One hero metric per screen/card, always.** Never open on a wall of equal-weight panels — that's the current Grafana problem this whole doc exists to fix.
2. **Everything else is one tap away, not zero and not three.** A hint (a chevron, a "View all" link, a partially-visible next card in a carousel) signals more data exists without showing it all at once.
3. **Group by the same metric families as the color system** (Activity, Body, Heart, Sleep) — the color a category owns should be the same everywhere it appears, so a coral accent always means heart rate, never something else on a different screen.
4. Follow the existing dataviz skill rules underneath all of this: one hero figure per view, one axis per chart, a legend only when ≥2 series share a chart, direct end-labels over legends when there's only one line.

## 8. Planned but not built yet

The user mentioned a **third panel/model** — read as an AI-generated insight panel (matching the "Insight" callout in the fasting-tracker reference screenshot) — to be placed center or side later. Noted here so it isn't lost, but explicitly deferred: build the static Insight Callout component now (per §5), wire an actual model into it as a separate follow-up task once the base UI overhaul is done.

## Implementation — `BioTwin/garmin-dashboard-app/`

Decisions made: Next.js (App Router, TypeScript, Tailwind v4), new folder inside `BioTwin/`, **replaces Grafana as the demo** (Grafana + InfluxDB + `garmin-fetch-data` still run in the background purely to keep the data pipeline fed — nobody looks at Grafana directly anymore).

**Stack:** Next.js 16 + shadcn/ui (`components.json` configured) + `lucide-react` + `next/font/google` (Inter + Playfair Display) + Route Handlers as the API layer in front of InfluxDB (`lib/influx.ts` — plain `fetch` against InfluxDB's HTTP query API, no SDK needed).

**Structure:**
- `app/page.tsx` — the dashboard, a Server Component that queries InfluxDB directly server-side (no internal HTTP round-trip) via `lib/health-data.ts`.
- `app/api/{summary,heart-rate,steps}/route.ts` — same queries exposed as JSON endpoints, for any client-side/future consumer.
- `components/health/*` — `LiveHeartCard` (client component, connects directly to the *existing* `ble_hr_live.py` WebSocket at `ws://localhost:8765/ws` rather than rebuilding that pipeline — genuinely live, confirmed updating in real time in a running screenshot), `MetricCard`, `Sparkline` (canvas, 2px line + 10% opacity fill per the dataviz skill's mark specs), `IconBadge`, `Carousel` (swipe on mobile, real CSS grid at `lg:` so desktop isn't just a stretched phone view), `InsightCard` (static placeholder for §8).
- Theme tokens live in `app/globals.css` as the validated hex values directly (not the shadcn default oklch grays) — `--coral` / `--violet` / `--teal` / `--amber` plus their `-fill` pastels, and `--good` / `--warning` / `--critical` status colors.
- PWA: `app/manifest.ts` + generated icons at `public/icon-{192,512}.png`.

**Run it:** `cd BioTwin/garmin-dashboard-app && npm run build && npm run start -- -p 3001` (or `npm run dev` while iterating). Reads InfluxDB at `localhost:8086` / database `GarminStats` by default (override via `INFLUX_HOST`/`INFLUX_PORT`/`INFLUX_DATABASE` env vars) — the existing `garmin viz dashboard` Docker stack must be running.

**Real bug found and fixed along the way:** `DeviceSync` has both a *tag* and a *field* named `Device` (from the upstream Python ingestion code) — querying `"Device"` directly returns nothing (empty `series`, no error) because of the name collision. Use the `Device_Name` field instead, which holds the identical value with no collision. This is a pre-existing quirk in the Python ingestion side, not something fixed there — only worked around in this app's queries.

**Verified, not assumed:** built and screenshotted at both 390px and 1280px viewports via a headless Playwright script (`chromium-cli` wasn't available in this environment) before calling this done — zero console errors, confirmed real data end-to-end (build → prod server → `/api/summary` → rendered page), confirmed the live BPM value actually changing between two screenshots taken seconds apart.

**Still open / not built:**
- The AI insight model itself (§8) — only the static UI slot exists.
- Dark mode (design doc and implementation are both light-only; the spec never asked for dark mode, so it wasn't built).
- Only Heart Rate / Steps / Sleep / Active Calories are wired up. Other measurements the Python side already collects (stress, body battery, activities/GPS, strength training) aren't surfaced yet — same pattern (`lib/health-data.ts` + a `MetricCard`) extends to each.
- Not yet made an actual installable PWA end-to-end (manifest + icons exist; no service worker/offline caching was added — ask if that's wanted, since a service worker adds real complexity around cache invalidation that wasn't clearly in scope here).
