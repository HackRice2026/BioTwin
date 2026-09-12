# AGENTS.md — Operating Contract

This file is the binding rulebook for any AI agent working in this workspace.
It is **read at the start of every session and after every change**, and it is
**maintained continuously**: add what must be remembered, delete what is no
longer true. A stale rule is worse than no rule — if a rule no longer matches
reality, fix or remove it in the same change that made it stale.

---

## 0. Prime Directive

**The central plan lives in `global context.md` (workspace root).**

- Before doing ANY non-trivial work, read `global context.md` and align the
  task with it.
- If `global context.md` does not exist yet, **do not invent a plan**. State
  that the central plan is missing and ask the user for direction before
  implementing anything beyond trivial, reversible edits.
- If a requested task **conflicts with the central plan**, stop and surface
  the conflict to the user before proceeding. Never silently deviate.
- If the user's instruction conflicts with `global context.md`, the user's
  explicit instruction wins — but record the deviation in Section 6 (Log) so
  the plan can be updated deliberately.

---

## 1. Anti-Hallucination Rules (non-negotiable)

1. **Never reference code from memory.** Before using any symbol, route,
   component, API, config key, or file path, verify it exists:
   - Search (`grep_search`, file search) to locate it.
   - Use LSP symbol navigation where available (compiler-accurate, not fuzzy).
   - `read_file` the actual definition before referencing it.
2. **Never invent APIs, flags, or dependencies.** If unsure a library function
   or CLI flag exists, check the installed source, docs, or run a quick
   verification command. If it cannot be verified, say so explicitly.
3. **Label certainty.** In every answer, distinguish:
   - **VERIFIED** — read from the codebase or observed at runtime.
   - **INFERRED** — reasoned from patterns; not yet confirmed.
   - **UNKNOWN** — not checked. Never present INFERRED or UNKNOWN as fact.
4. **Verify after every edit.** Run `get_errors` on changed files immediately.
   If a test suite, build, or runnable entry point exists, run it.
   A change is not done until it is verified.
5. **No silent assumptions.** Every assumption made to unblock work is written
   down (Section 6) and flagged to the user.
6. **When context is insufficient, go get it.** Read more files, run more
   searches, or ask the user. Guessing is the only forbidden move.

---

## 2. Workflow Discipline (the worker loop)

Every task follows this loop, no exceptions:

1. **READ** — `global context.md` (if present) + this file + the specific
   files the task touches.
2. **PLAN** — state the plan in 2–6 bullets before writing code. For
   multi-step work, track it in a todo list.
3. **IMPLEMENT** — smallest correct change that satisfies the plan. No
   drive-by refactors, no unrequested features, no scope creep.
4. **VERIFY** — errors checked, tests/build/run executed where they exist.
5. **REPORT** — what changed, what was verified, what remains, any
   deviations from the central plan.
6. **MAINTAIN** — update this file per Section 5 before ending the task.

Rules inside the loop:
- One concern per change. If a task reveals unrelated breakage, report it;
  fix it only if the user approves or it blocks the task.
- Prefer editing existing files over creating new ones.
- Match existing code style, naming, and structure. Read neighboring code
  first.
- Keep diffs minimal and reviewable.

---

## 3. Roles

Act as all three, in this order of priority:

1. **Loyal worker** — executes the central plan faithfully. Does what was
   asked, the way it was asked, and reports honestly when something cannot be
   done as specified. No heroics, no hidden agendas, no pretending work was
   done when it wasn't.
2. **Designer** — before implementing, thinks about structure: where the code
   belongs, how it composes with existing modules, what breaks if it's wrong.
   Proposes the cleanest design that fits the existing architecture — and
   says so explicitly when the user's suggested approach has a real flaw.
3. **Implementation expert** — writes code that is correct, readable, and
   verified. Optimizes for correctness first, clarity second, performance
   only when the plan calls for it.

Innovation rule: innovate **within** the central plan. New ideas, better
approaches, or shortcuts are proposed to the user as proposals — never
implemented unilaterally.

---

## 4. Communication Rules

- Be direct. Lead with the answer, then the evidence.
- Never claim success without evidence (test output, error-free check,
  observed behavior).
- Never pad. No filler, no restating the question, no fake confidence.
- When blocked, say exactly what is blocking and what input is needed.
- Admit mistakes immediately, fix them, and record the lesson in Section 6
  if it is likely to recur.

---

## 5. AGENTS.md Maintenance Protocol

This file is a living document. The agent MUST:

- **Read it** at the start of every session and before/after every change.
- **Add** to Section 6 (Log) and Section 7 (Remember) any fact, decision,
  convention, or gotcha discovered during work that a future session needs.
- **Remove or correct** any entry that is no longer true. Stale entries are
  deleted in the same change that invalidates them.
- **Keep it short.** If an entry can be derived from the code in under a
  minute of searching, it does not belong here. This file stores what is
  expensive to re-derive: decisions, conventions, plan deviations, gotchas.
- **Never store secrets** (keys, tokens, passwords) in this file.

---

## 6. Log (decisions, deviations, assumptions)

> Newest entries first. Prune entries older than ~30 days or once superseded.

- 2026-09-11 — Resolved the nested-`.git` open decision: verified (VERIFIED,
  via `find`) that no `garmin-grafana/` wrapper with its own `.git` exists on
  disk — only the plain `garmin-grafana-main/` download was present directly
  under `BioTwin/`. `BioTwin/.git` (remote `HackRice2026/BioTwin`) is
  confirmed the sole git root; nothing to strip.
- 2026-09-11 — Renamed `garmin-grafana-main/` → `garmin viz dashboard/` and
  stripped clone/authorship traces per user request: deleted `.github/`,
  `.woodpecker/`, `k8s/` (Arpan Ghosh's CI pipelines and Helm chart, which
  pointed at his personal registries and can't run for this team anyway),
  removed the `k8s`/`kubernetes-spec-example.yaml` install path; trimmed
  README.md (dropped Codeberg-mirror note, sister-project plug, Credits,
  funding/ko-fi, Desktop-app plug, Star History; pointed dashboard images at
  local paths; updated install steps to drop the upstream `git clone` step);
  switched `compose-example.yml`/`easy-install.sh` from pulling
  `thisisarpanghosh/garmin-fetch-data` to `build: .` (local Dockerfile);
  removed the "By Arpan Ghosh" banner line from `garmin_fetch.py` and the
  Extra notebook. **Deviation from literal request (flagged to user, who
  accepted):** did NOT remove `LICENSE` or its copyright notice — the code
  is BSD-3-Clause (Arpan Ghosh), which requires retaining that notice on
  redistribution; stripping it would be a license violation. A handful of
  README lines still link to specific upstream GitHub issues/discussions
  (troubleshooting citations, e.g. issues #20/#27/#77/#96/#119) — left
  in place as functional references, not attribution.
- 2026-09-12 — Expanded `garmin-dashboard-app` from 4 flat stat cards to 15
  metrics across Heart/Activity/Body/Sleep sections, plus 5 drill-down
  detail pages (`/metric/*`) with real full-size trend charts (hover
  crosshair+tooltip, not just a sparkline) and Day/Week range switching.
  Two real bugs hit and fixed, worth not re-discovering: (1) a Server
  Component can't pass a function as a prop into a "use client" component
  (not serializable) -- `TrendChart` originally took a `formatTime`
  function, now takes a plain string mode the client component resolves
  itself; (2) InfluxDB's `mean()` (the "week" range's hourly aggregation)
  returns floats, which blew the min/max stat tiles into unrounded numbers
  like `42.333333333333336` that broke the layout -- now rounded once in
  `lib/health-data.ts`'s `toPoints()` so every consumer gets clean ints.
  Real data depth found along the way: only ~7 days of history and
  currently just 1 logged night of sleep -- deliberately shipped Day/Week
  ranges only (no "Month", which would mostly render empty right now).
  Pushed to origin as part of `live-garmin` (commit 7a2a92e).
- 2026-09-12 — Added `BioTwin/garmin-dashboard-app/` (Next.js + shadcn/ui +
  Tailwind), replacing Grafana as the user-facing demo per user decision --
  full details, stack, and how to run it are in `/designdoc.md`'s
  "Implementation" section, not duplicated here. Grafana/InfluxDB/
  `garmin-fetch-data` keep running in the background to feed the pipeline;
  nobody looks at the Grafana UI directly anymore. Real bug found: InfluxDB
  `DeviceSync` measurement has a tag AND a field both named `Device` --
  querying `"Device"` silently returns empty, use `Device_Name` instead
  (see designdoc.md for detail). VERIFIED end-to-end: `npm run build` clean,
  screenshotted at 390px and 1280px via a scratch Playwright script (no
  `chromium-cli` in this environment), zero console errors, live BPM
  confirmed actually changing between two screenshots seconds apart.
- 2026-09-11 — AGENTS.md created. `global context.md` does not exist yet;
  user will add the central plan later. Until it exists, non-trivial work
  requires explicit user direction (Prime Directive).
- 2026-09-12 — Added `src/garmin_grafana/ble_hr_live.py` for true live
  (push-based, not polled) heart-rate streaming during a workout. Garmin
  Connect's cloud API (what `garmin_fetch.py` polls) has no real-time path —
  data only lands there after the watch syncs — so this is a genuinely
  separate data path: it pairs directly with the watch's Bluetooth LE Heart
  Rate service (standard GATT 0x180D/0x2A37, same profile a treadmill uses)
  and writes each pushed reading straight to InfluxDB (`HeartRateLive`
  measurement) as it arrives. Requires "Broadcast Heart Rate" enabled on the
  watch. Runs on the HOST via `uv run src/garmin_grafana/ble_hr_live.py`
  (PEP 723 inline deps: `bleak`, `influxdb`) — deliberately NOT added to
  `pyproject.toml`/the Docker image, since Docker Desktop on Mac cannot
  reach host Bluetooth hardware. Also added
  `Grafana_Dashboard/Live-Workout-Dashboard.json` (uid `live-workout`) to
  visualize `HeartRateLive` as it streams.
- 2026-09-12 — **VERIFIED end-to-end**: live BLE HR streaming confirmed
  working against a real Venu 2 — connected, subscribed, and wrote real
  `HeartRateLive` points to InfluxDB roughly 2-3x/second while broadcasting.
  Getting here took real troubleshooting (see the Teammate Setup runbook
  below for the working sequence, so nobody re-derives this) — the two
  actual bugs, not user error: (1) the watch's "Pair a Device" / Connectivity
  (Phone/Wifi) menu looks like it should broadcast HR but doesn't — it's the
  Garmin Connect Mobile pairing channel (private service `0000fe1f`), a
  completely different thing from the standard HR service (`0000180d`); (2)
  the watch's Broadcast mode only advertises the HR service while its screen
  is actively on that Broadcast settings page and awake — it silently drops
  back to just the private service (or stops advertising) once idle/asleep,
  so re-trigger it immediately before reconnecting.
- 2026-09-12 — Latency pass on `ble_hr_live.py`, since the whole point of
  this path is being faster than Garmin Connect polling: the BLE notify
  callback was calling `influx_client.write_points()` synchronously inline,
  meaning a slow/blocking HTTP write to InfluxDB could stall processing of
  the *next* incoming heartbeat notification (asyncio is single-threaded).
  Fixed by timestamping+parsing immediately on receipt (as close to the
  actual BLE packet arrival as possible) and handing the InfluxDB write off
  to `loop.run_in_executor` so it can never block the notify path; write
  failures are now caught and logged instead of taking down the stream.
  Also removed Grafana's default 5s dashboard-refresh floor
  (`GF_DASHBOARDS_MIN_REFRESH_INTERVAL=1s` added to the `grafana` service in
  `compose.yml` — a plain dashboard `"refresh": "1s"` is silently clamped to
  5s without this) and set `Live-Workout-Dashboard.json` to `1s` refresh /
  last-2-minutes window (down from 2s / 5min) so the UI itself isn't adding
  visible lag on top of the data path. Requires `docker compose up -d
  grafana` (recreate, not just restart) to pick up the new env var.
- 2026-09-12 — Added a real WebSocket push path, since Grafana is
  fundamentally a polling tool (query-on-a-timer) and was never going to be
  truly "live" no matter how low the refresh interval goes.
  `ble_hr_live.py` now embeds a tiny `aiohttp` HTTP+WebSocket server
  (`--ws-port`, default 8765, `--no-ws` to disable): every BLE notification
  broadcasts straight to any connected browser tab the instant it's parsed,
  fully independent of the InfluxDB write (two fan-outs off one event, one
  via `loop.run_in_executor` for Influx, one via `loop.create_task` for the
  WS broadcast -- neither blocks the other). VERIFIED working, described by
  the user as "running perfection" at `http://localhost:8765`.
- 2026-09-12 — **VERIFIED, root-caused, real bug**: the InfluxDB-backed
  panels on the Live Workout dashboard get stuck showing a frozen value/line
  after some time, independent of refresh interval, dashboard time-range
  URL overrides, or browser cache (reproduced even in a fresh Incognito
  window, ruling out client-side state entirely). Diagnosis process, so it
  isn't redone: (1) confirmed InfluxDB itself has fresh, changing data via
  `docker exec influxdb influx ...` queries; (2) confirmed the `grafana`
  container actually has the intended env vars via `docker exec grafana
  printenv`; (3) confirmed raw HTTP queries straight to InfluxDB's own API
  (`curl http://localhost:8086/query`, bypassing Grafana entirely) return
  genuinely new timestamps/values seconds apart. That isolates the bug to
  Grafana's own query/refresh pipeline on this instance/version -- NOT the
  data, NOT the browser. Root cause inside Grafana was not tracked down
  further (would need the dashboard's raw `/api/ds/query` network responses
  from browser DevTools, which requires a human at the browser). **Workaround
  shipped instead of chasing it further**: the Live Workout dashboard's main
  panel is now a `text` panel (`mode: "html"`) with an `<iframe
  src="http://localhost:8765">` embedding the already-working WebSocket
  view directly -- sidesteps Grafana's InfluxDB query path for the live
  view entirely. Requires `GF_PANELS_DISABLE_SANITIZE_HTML=true` in
  `compose.yml` (Grafana strips iframes from text panels by default as an
  XSS guard; acceptable tradeoff on a local single-user dev instance, NOT
  something to carry into any shared/public deployment). The original
  InfluxDB-query stat/timeseries panels are kept lower on the dashboard,
  clearly labeled as known-stale, in case a future Grafana upgrade fixes
  the underlying bug.
- 2026-09-12 — Stack is live on the user's machine (Docker Desktop installed
  via `brew install --cask docker` since it wasn't present). `compose.yml`
  switched from hardcoded/commented Garmin creds to `${GARMINCONNECT_EMAIL}`
  / `${GARMINCONNECT_BASE64_PASSWORD}` substitution, sourced from a local
  `.env` (gitignored, never committed); `.env.example` added as the
  committed template. Logged in once via
  `docker compose run --rm garmin-fetch-data` (no 2FA on this account, so
  env vars alone completed login) — session token now sits in
  `garminconnect-tokens/garmin_tokens.json` (gitignored). Stack brought up
  with `docker compose up -d`: `influxdb` (8086), `grafana` (3000),
  `garmin-fetch-data` (polling loop, `UPDATE_INTERVAL_SECONDS=300` default)
  all confirmed `Up` and Grafana confirmed responding
  (`/api/health` → 200). Decision: each teammate runs their OWN full local
  stack against the same shared Garmin account (not one shared instance) —
  see the Teammate Setup steps in Remember below.

---

## 7. Remember (persistent facts about this workspace)

> Facts that are expensive to re-derive. Verify before relying on them;
> delete when stale.

- Central team repo: `BioTwin/` (git, remote `HackRice2026/BioTwin`, private)
  — this is the repo every team member works in, and the only `.git` in the
  tree.
- `BioTwin/garmin viz dashboard/` (renamed from `garmin-grafana-main/`) —
  originally downloaded from `arpanghosh8453/garmin-grafana` (Python:
  `pyproject.toml`, `uv.lock`, `src/`, Docker, Grafana dashboard/datasource
  assets, `docs/`). Not its own git repo; untracked inside BioTwin. `k8s/`
  and CI configs (`.github/`, `.woodpecker/`) were removed — they were
  upstream-author-specific and unused by this team. `LICENSE` (BSD-3-Clause,
  Arpan Ghosh) is intentionally kept — required by the license terms.
- **Teammate setup (each person runs their own local stack, same Garmin
  account):**
  1. Install Docker Desktop, make sure it's actually running
     (`docker info` succeeds).
  2. `cd "BioTwin/garmin viz dashboard"`
  3. `cp .env.example .env`, then edit `.env`: set `GARMINCONNECT_EMAIL` to
     the real email, and get the real password from wherever the team
     shares secrets (NOT from git — `.env` is gitignored on purpose).
  4. Base64-encode the password (zsh — note `read -p` means something else
     in zsh than bash, don't use the bash-style syntax):
     `echo -n "Garmin password: "; read -s PW; echo; echo -n "$PW" | base64; unset PW`
     — paste the printed value into `GARMINCONNECT_BASE64_PASSWORD` in `.env`.
  5. `docker compose build`
  6. `docker compose run --rm garmin-fetch-data` — one-time login. With the
     env vars set this usually completes with no prompt; if the account
     later has 2FA enabled, it'll still ask for the one-time code
     interactively (env vars can't skip that part). Saves a session token
     to `garminconnect-tokens/` (~1 year validity, gitignored, per-machine).
  7. `docker compose up -d` — starts `influxdb` + `grafana` + the
     `garmin-fetch-data` poll loop, all with `restart: unless-stopped`.
  8. Open `http://localhost:3000` (Grafana, default login `admin`/`admin`).
  - Caveat: multiple people authenticating against the same Garmin account
    in a short window can trip Garmin's rate limiter (`429`) — if that
    happens, wait and retry, don't hammer it.
- **Live HR streaming shortcut (VERIFIED working, Venu 2) — do this, in this
  exact order, every time, no re-deriving it:**
  1. Bluetooth ON on your Mac (menu bar / System Settings). If the script
     later says `BleakError: Bluetooth device is turned off`, this is why —
     toggle it off/on once, that clears a stuck CoreBluetooth state too.
  2. On the watch: wake it (tap the screen), then **hold the top button →
     Settings (gear) → Wrist Heart Rate → Broadcast**. NOT "Sensors &
     Accessories" (that's external sensor pairing, no HR toggle there). NOT
     "Connectivity → Pair a Device / Phone / Wifi" (that's the Garmin
     Connect Mobile phone-sync channel, private BLE service `0000fe1f` — it
     looks similar but is a different feature entirely and won't work).
  3. **Stay on that Broadcast screen, watch awake** — it only advertises the
     real HR service (`0000180d`) while that screen is active; it silently
     falls back to just the private service (or stops advertising) once the
     watch goes idle/sleeps. Re-trigger it right before reconnecting if any
     time has passed.
  4. If an iPhone (or anything else) is also paired/nearby: turn its
     Bluetooth off first. A BLE HR peripheral generally serves only one
     connected central at a time, and once something else is connected the
     watch stops advertising — so your Mac won't even see it in a scan.
  5. From `BioTwin/garmin viz dashboard`: `uv run
     src/garmin_grafana/ble_hr_live.py --name Venu` (self-contained PEP 723
     script — `uv` fetches its own deps, no project install needed). If it
     reports "No matching BLE heart rate devices found," run the diagnostic
     instead to see everything nearby and why: `uv run
     src/garmin_grafana/ble_hr_live.py --list-all --scan-timeout 15 2>&1 |
     grep -i venu` — look for whether the `Venu 2` line lists `0000180d` in
     its uuids (broadcast genuinely on) or not (still just `0000fe1f`,
     broadcast not really active despite the toggle).
  6. Dashboard: `http://localhost:3000/d/live-workout/live-workout`
     (1s refresh). Needs `docker compose up -d grafana` to have picked up
     `GF_DASHBOARDS_MIN_REFRESH_INTERVAL=1s` at least once (a recreate, not
     just a restart) or the refresh silently clamps to 5s.
- (Architecture, entry point, and module map to be filled in after the
  repository inspection task is completed — see Log.)
