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

- 2026-09-12 — New UI entry is `BioTwinApp.tsx` with `biotwin.css`; data
  loading lives in `useDashboard`, reusable page content in `DashboardPanels`.
  Connections stays mounted across tabs so direct Bluetooth does not drop
  when leaving its page. Old App/style remain temporarily for comparison
  until the real voice and navigation checks pass, then must be removed.
  Product diagnostics removed; avatar movement/view controls and both GPU
  audio fan-outs remain. Verified renders at 1440px and 390px: no page errors
  or horizontal overflow. The two viewports use distinct navigation/layouts.

- 2026-09-12 — Body Battery is an explicitly unvalidated presentation estimate:
  80% existing readiness + 20% live recovery progress, using readiness alone
  when the live pulse is stale/missing, and null when readiness is missing.
  It never treats missing recovery as zero and never overwrites Garmin’s
  reported battery. The optional state field and narration facts share the
  server-computed value; active calories are also now available to narration.

- 2026-09-12 — BioTwin 2.0 speech supports optional timestamped NDJSON on
  the existing account-scoped, single-use ticket endpoint. Caption timing
  follows audio currentTime; only the ended event triggers automatic return.
  Microphone questions use the existing recorded-audio transcription endpoint
  so the Vertex path is exercised in every supported recording browser.
  Topic detection consumes the question before the provider request.

- 2026-09-12 — Shivendra authorized recording the full BioTwin 2.0 redesign
  in `global context.md`; it is now the central plan. User overrides the
  default dev workflow: implement on `biotwin2.0` (base `ccfe601` from dev),
  with logical commits as Shivendra using the existing configured email.
  Preserve existing PWA icons and both avatar GPU integrations. Design
  assumption: the persistent Body Battery is a labeled BioTwin estimate
  from existing computed signals, separate from Garmin’s measured score.

- 2026-09-12 — Origin checking is enforced in **three separate places** in
  core/api.py, not one: `CORSMiddleware`'s `allow_origins` (~line 97), the
  custom `protections` middleware for POST/PUT/DELETE (~line 108), and the
  `/ws/live` WebSocket handler's own inline check (~line 828) -- each had
  its own hardcoded `[config.frontend_origin, config.public_url]` list.
  When `lan_origin` was added earlier for LAN/phone access, only the
  middleware got it; the other two still silently rejected that origin
  (WS closes with code 1008, no error surfaced to the user beyond the
  frontend showing "offline"). All three now include `config.lan_origin`
  when set. Found via a real symptom, not inspection: accessing over
  `127.0.0.1` instead of `localhost` (same root cause, different browser)
  showed "offline" with the WebSocket connection failing.
  **If you add a fourth origin allowance in the future, grep for
  `frontend_origin` and `public_url` together in core/api.py first --
  there may be more than one spot to update, this file does not
  centralize the allowed-origins list.**

- 2026-09-12 — Added Vertex AI as a second, opt-in narration backend
  (`use_vertex_narration` in core/config.py; `_vertex_narrate()` in
  narration/service.py) alongside the existing AI Studio key, after
  confirming by direct API call that the AI Studio key's "prepay credits"
  billing bucket is genuinely separate from the project's normal Cloud
  Billing account/card -- linking billing and adding a card there did not
  fix it, but the same account/project works immediately through Vertex AI.
  Full setup steps in Section 7 ("Vertex AI narration setup"). Both the
  local dev path and the Docker path (`ops/docker-compose.yml`, mounting
  each person's own `~/.config/gcloud/application_default_credentials.json`
  read-only) were built and VERIFIED with a real end-to-end call each,
  not just config changes -- see Section 7 for the exact evidence.
- 2026-09-12 — Consolidated three diverged lineages (`main`, `live-garmin`,
  a nearly-empty `dev`) onto `dev` as one squashed commit, then branched
  `agentic-calendar` from it for real-calendar agentic work: Google Calendar
  (real OAuth, connected and VERIFIED against the user's actual account --
  a booked event's returned Google `htmlLink` decodes to `rizsaurav@gmail.com`,
  not a mock) and Outlook Calendar (Graph API, built and unit-tested with a
  mocked transport; real credentials not yet supplied). Added
  `CalendarService.seed_if_empty()` -- writes a representative week (4
  classes, 20 work hours, 5 meetings) only when the connected calendar has
  nothing in the next 7 days; refuses outright otherwise. Built
  `LiveSchedule` (frontend/src/LiveSchedule.tsx): asking "when should I
  workout today" in chat (keyword match, deliberately bypasses the
  Gemini narration path, which is locked to explaining not booking) opens
  an animated day-timeline that finds the best-scored workout proposal
  from the existing readiness-aware planner, proposes it by voice
  (browser speechSynthesis, not ElevenLabs -- works without that key
  configured) and on confirmation books it through the same
  `/api/calendar/events` path the Daily Plan page already used.
  Squash-merging `dev` from `live-garmin` breaks git's ability to
  fast-path-merge later commits from the original unsquashed `main`
  lineage for files touched in that squash (shows as spurious add/add
  conflicts even when one side is a pure superset) -- expect this on
  every future `main` -> `agentic-calendar` merge until the branches
  reconverge properly; diff both conflict sides before resolving rather
  than assume real divergence.
  Gemini narration: `NARRATION_API_KEY` authenticates successfully
  (VERIFIED via a direct call to the configured endpoint) but the
  Google AI Studio project's prepayment credits are depleted (429
  RESOURCE_EXHAUSTED) -- needs billing added at ai.studio/projects,
  not a config fix. `.env` is never in git (confirmed: gitignored,
  zero history on any branch, ever) -- a value missing from it cannot
  be recovered from an old commit, only re-entered.
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
- 2026-09-12 — Four `3d-gesturing` reports fixed in one pass, each verified
  before/after rather than assumed:
  1. "GPU FACE SERVICE: FALLBACK" was a closed SSH tunnel, not a dead
     service -- `curl` straight to the SCC host confirmed the remote
     service itself is healthy and reachable, just still running as
     `procedural_audio_fallback` / `model_loaded:false` (the known,
     already-documented limitation -- real NVIDIA Audio2Face was never
     installed there). Opened `ssh -N -L 8765:localhost:8765 scc` locally;
     badge flips to ONLINE. See Remember -- this isn't automatic.
  2. Swapped in the new ARKit export (was sitting as a stray, untracked
     `docs/model (1).glb`) as the default `frontend/public/assets/model.glb`.
     Did not swap blindly: parsed both GLBs' binary JSON chunks directly and
     diffed skeleton joints (73/73 identical names) and morph target /
     blendshape names (51/51 identical) before touching anything, since the
     avatar code binds animation by name, not index. Only difference was
     outfit material naming (`outfit_bottom/outfit_shoes/outfit_top` ->
     single `outfit`, plus a new `haircut` material) -- nothing in code
     references those specific names, so harmless. Old file backed up
     outside the repo, not committed.
  3. Root-caused "hey, hi" getting an irrelevant readiness/sleep data-dump
     instead of a greeting: `narration/service.py`'s `SYSTEM_PROMPT` had
     zero handling for small talk, so Gemini/Vertex defaulted to narrating
     the day's stats for literally any input, including "hey, hi" and
     "thanks". Added one line permitting a brief natural reply with empty
     evidence for greetings/small-talk/thanks. Verified with direct
     `POST /api/twin/ask` calls before and after the change (before: full
     readiness paragraph; after: "Hi there!" / "You're welcome!").
  4. `model.glb` is and always was tracked in git (not gitignored, checked
     `git ls-files` directly) -- a teammate on the same branch seeing a
     different model is a stale checkout or a cached browser response, not
     a repo/gitignore problem. See Remember for the exact check to run.
- 2026-09-12 — Two more real bugs reported straight from a screenshot, both
  fixed and verified:
  1. Idle pose had both arms stuck out near the GLB's T-pose bind rotation
     ("looks like a scarecrow"). `baseTransforms()` uses each bone's
     as-loaded rotation as the zero-point for every procedural offset, and
     idle only ever nudged the arm a few hundredths of a radian off that --
     fine only if the bind pose is already relaxed, which it is not (a
     near-horizontal T-pose, confirmed identical between this model and the
     previous one, so not something the model swap caused). Fixed in
     `frontend/src/Avatar.tsx` with one named offset constant applied under
     the same offset system gestures already use.
  2. Lip sync was "just opening and closing," reported verbatim -- true,
     because `services/avatar_face_service/app.py`'s `make_frame()` drove
     jawOpen/mouthFunnel/mouthPucker/mouthStretch all off the same sine
     wave(s), so every shape scaled together instead of forming distinct
     mouth shapes. Replaced with a small set of distinct viseme-like target
     shapes the existing phase counter now cycles and smoothstep-blends
     between. Still fully procedural (no audio content analyzed, just
     energy + a cycle timer) -- not a step toward real Audio2Face, just a
     less-bad placeholder. Deployed straight to the running instance on the
     SCC box and verified live over the actual WebSocket through the
     existing tunnel: returned frames now hit qualitatively different
     shapes in sequence instead of all rising and falling together.
  3. Deploying #2 taught a real lesson the hard way -- see Remember, tmux
     `exec` gotcha. Took the whole `avatar-face` tmux session down for
     about a minute by sending it C-c; recovered by recreating the session
     and rerunning `start.sh`, no data lost, but worth not repeating.
- 2026-09-12 — Two more requests, handled together: seed a teammate's data
  (see the onboarding script entry above) and replace the lip-sync
  heuristic with "an actual model actually serving," not more heuristic
  tuning. On the model: checked thoroughly for NGC/NVIDIA registry
  credentials (this machine, the SCC box's docker config, saurav's env and
  home directory) to pull the real Audio2Face-3D NIM as originally
  planned -- genuinely nothing found, GPU/Docker/disk were all otherwise
  ready. User's call (asked directly): use a real open-source model
  instead of waiting on NVIDIA credentials. Deployed
  `facebook/wav2vec2-base-960h` (real ASR, GPU-accelerated) in
  `services/avatar_face_service/app.py`, replacing the procedural
  generator -- full details, and the honest scope of what this is and
  isn't, are in `docs/AVATAR_IMPLEMENTATION_PLAN.md`'s "Lip sync: what
  changed" section. Verified end-to-end through the real production
  WebSocket (local tunnel -> SCC box -> model -> back): service logs show
  real inference completing (first call ~340ms cold, then consistently
  under 30ms) and the returned mouth shapes tracking actual audio content.
  First attempt used `facebook/wav2vec2-lv-60-espeak-cv-ft` (outputs real
  IPA phonemes, would have been a better mapping than letters) but its
  `phonemizer` dependency couldn't detect a genuinely-present, working
  espeak/espeak-ng install (installed both `espeak-ng` and `espeak`,
  confirmed both run fine standalone, `phonemizer` still reported "espeak
  not installed") -- a real unresolved library compatibility issue, not a
  missing-package problem; abandoned in favor of the plain-English model
  rather than sinking more time into it.
- 2026-09-12/13 — Reported: idle-pose fix had an elbow-flare regression
  ("hands tucked in, looks like a duck"), and separately, the avatar
  barely moves during conversation (no hand gestures while talking,
  legs never move/walk). Fixed the flare (see Remember). Root-caused
  the movement complaint: only two keyword triggers exist anywhere in
  the frontend that ever set `action` away from `"idle"` ("show me
  squat", "I'm exhausted") -- walk/run/point/celebrate exist in
  Avatar.tsx but nothing in real conversation ever calls them, and the
  speaking-only arm sway is a small few-degree wobble. This led into
  the real fix: real full-body gesture generation, added below.
- 2026-09-13 — Added real full-body co-speech gesture generation
  (EMAGE, `PantoMatrix/PantoMatrix`) as a second GPU service running
  parallel to the face service, per direct user request after
  confirming (WebSearch + reading the actual GitHub repo/HF model card,
  not assumed) that EMAGE's weights are Apache-2.0 even though its code
  repo has no license at all -- user explicitly chose to proceed anyway
  after being told this plainly. Full technical writeup (model, venv,
  the retargeting sign-convention finding, the streaming architecture,
  a real bug found and fixed via an actual failing test, both
  verification passes) is in `docs/AVATAR_IMPLEMENTATION_PLAN.md`'s
  "Body gestures" section, not duplicated here. Headline result,
  verified twice: a real authenticated conversation (logged in as
  `sapnil`) shows the avatar's arms genuinely raised and gesturing
  while "Speaking..." is shown, driven by real GPU inference logged in
  real time -- not the old flat idle pose with a faint wobble.
  Per explicit instruction from this point on: **do not merge
  `3d-gesturing` into `dev`** until told the 3D work is ready -- commit
  and push to the feature branch only.
- 2026-09-13 — Also finished, per explicit request, the other half of
  "real model, not heuristics": added finger retargeting (30 more
  joints) and cross-window motion continuity to the EMAGE body service,
  and separately, actually built and ran the real NVIDIA Audio2Face-3D
  SDK end to end on the SCC H100 -- CUDA 12.9 + TensorRT 10.13 via
  NVIDIA's normal apt repo (no NGC/gated access needed for the SDK or
  its non-emotion models), full CMake build, real ONNX-to-TensorRT
  engine conversion, real inference on real audio, both the regression
  and diffusion model variants. This is NOT wired into the app: checked
  the model's own metadata before assuming anything, and its output is
  NVIDIA's own proprietary per-character shape/vertex basis (their
  "mark"/"claire"/"james" meshes), not ARKit blendshapes -- the "outputs
  ARKit Blendshapes" claim describes the separate, still-gated NIM
  microservice, not this open SDK. Using this on our avatar would need
  a real mesh-retargeting project, not a quick follow-up. Full detail
  in docs/AVATAR_IMPLEMENTATION_PLAN.md's new Audio2Face-3D section.

---

## 7. Remember (persistent facts about this workspace)

> Facts that are expensive to re-derive. Verify before relying on them;
> delete when stale.

- `scripts/*.py` import `core`/`shared` as top-level packages, which only
  resolve if the project root is on `PYTHONPATH` -- `uv run
  scripts/whatever.py` alone fails with `ModuleNotFoundError: No module
  named 'core'` (a plain script run puts the script's OWN directory on
  `sys.path`, not the cwd). Run these as `PYTHONPATH=. uv run
  scripts/whatever.py` from the repo root instead.
- `scripts/onboard_teammate.py` gives a teammate their own login seeded
  with a replay copy of another account's history (default source:
  `demo`) via the existing `runtime.ingest(..., broadcast=False)` +
  `Provenance.REPLAY` path -- the same mechanism `/api/ingest/file` already
  uses for FIT/JSON imports, not a new one. Real teammate accounts stay
  fully isolated (their own `user_id`, their own rows); this only copies
  data in, once per run, it does not link/alias accounts or give live
  shared read access. Re-run per teammate any time to refresh their copy.

- Central team repo: `BioTwin/` (git, remote `HackRice2026/BioTwin`, private)
  — this is the repo every team member works in, and the only `.git` in the
  tree.
- Branch topology (as of 2026-09-12): `main` is Shivendra's line (FastAPI +
  React/Three.js app, keeps moving -- check `git fetch` before assuming it's
  current). `dev` is the shared team working branch going forward, kept
  current with `main` via ordinary (non-squash) merges from here on. The
  active feature branch for calendar/voice/agentic work is
  `agentic-calendar`, branched from `dev`. The Next.js `garmin-dashboard-app`
  and `garmin viz dashboard` (InfluxDB + Grafana + BLE) live alongside the
  BioTwin app as sibling top-level directories on `dev`/`agentic-calendar`,
  not on `main`.
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
- **Vertex AI narration setup (each person who wants it running does this
  once, on whichever machine actually runs the server):**
  - Why this exists: an AI Studio key (`NARRATION_API_KEY`) bills through a
    separate "prepay credits" balance that's easy to accidentally deplete,
    independent of a project's normal Cloud Billing account/card — confirmed
    by hitting the real endpoint directly and getting `429
    RESOURCE_EXHAUSTED` / "prepayment credits are depleted" even with
    billing properly linked. Vertex AI bills through the project's ordinary
    Cloud Billing instead, so it can keep working when that prepay balance
    is the actual problem.
  1. Install the `gcloud` CLI if it isn't already (`brew install
     google-cloud-sdk` on a Mac).
  2. `gcloud auth application-default login` — opens a browser, log in with
     whichever Google account should own the usage/billing for this. This
     does **not** create a downloadable key file (some Google orgs block
     service-account key creation entirely via
     `iam.disableServiceAccountKeyCreation` — this method sidesteps that,
     it's also just the safer option regardless). Credentials land at
     `~/.config/gcloud/application_default_credentials.json`, gitignored
     territory by nature (outside the repo entirely), never committed.
  3. Note the Google Cloud project ID this account actually has Owner/Editor
     rights on (Cloud Console → top project switcher). A project AI Studio
     auto-created for you when you first generated a key may belong to a
     *different* identity than the one you just logged in as here — if so,
     `gcloud services enable aiplatform.googleapis.com --project=<id>` will
     fail with a clear `PERMISSION_DENIED`, which is exactly how to tell.
  4. `gcloud services enable aiplatform.googleapis.com --project=<id>` —
     one-time, needs to succeed before step 6.
  5. In `.env`: set `USE_VERTEX_NARRATION=true`, `ALLOW_EXTERNAL_NARRATION=true`,
     `VERTEX_PROJECT_ID=<id>` from step 3. `VERTEX_REGION` (default
     `us-central1`) and `VERTEX_MODEL` (default `gemini-2.5-flash`) usually
     don't need changing — VERIFIED this model/region pair actually serves
     content; `gemini-2.0-flash`/`gemini-2.0-flash-001` both 404 on Vertex
     even though they're valid AI-Studio-side model names, so don't assume
     an AI Studio model name carries over.
  6. Restart the server. A real answer (not the template fallback) confirms
     it: ask the twin anything, check the response's `mode` is
     `language_service` and `model` starts with `vertex:`.
  - Docker: `ops/docker-compose.yml` mounts
    `${GOOGLE_ADC_PATH:-$HOME/.config/gcloud/application_default_credentials.json}`
    (your own local ADC file from step 2, per-person, never baked into the
    image) into the container read-only at the path
    `GOOGLE_APPLICATION_CREDENTIALS` points to. VERIFIED working end to end:
    built the image, brought the full stack up with a real Postgres
    database, and got a real `mode: "language_service"` answer back from
    the containerized app, not just the local dev server.
  - Per-machine setups verified so far (each is a different teammate's
    account/project -- this is opt-in and per-person, so don't assume one
    entry covers another machine):
    - 2026-09-12: logged in as `launchboxed@gmail.com`, project
      `project-b0574b76-03df-42f0-956`.
    - 2026-09-12: logged in as `shivendrabhagat121@gmail.com`, project
      `project-1d1613d0-157c-4dbc-ad1`. VERIFIED with a real end-to-end
      `narrate()` call (fixture context, not just config wiring): got
      `mode: "language_service"`, `model: "vertex:gemini-2.5-flash"`.
    If either project's Vertex AI access or billing ever changes,
    re-verify with a direct call before assuming that entry still works --
    don't trust these notes past their date.
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
- The avatar's GPU face service tunnel is **not automatic**. Each dev
  session needs `ssh -N -L 8765:localhost:8765 scc` running locally, or the
  app silently shows "GPU FACE SERVICE: FALLBACK" with no error explaining
  why. Check `curl http://localhost:8765/health` locally to confirm the
  tunnel is actually up. The remote service currently always answers
  `"backend":"procedural_audio_fallback","model_loaded":false` even when
  healthy and reachable -- that's the known limitation (real NVIDIA
  Audio2Face/ACE was never installed on the SCC box), not a sign the
  tunnel is broken. Port 8765 is also used by an unrelated local BLE tool
  elsewhere in this repo (`--ws-port`, default 8765) -- if both are ever
  run on the same machine at once, one will fail to bind.
- Before swapping `frontend/public/assets/model.glb` for a different
  export: parse the GLB directly (read the GLB header, decode the JSON
  chunk with `JSON.parse`) and diff skeleton joint names (`skins[0].joints`
  -> `nodes[i].name`) and morph target names (`meshes[i].primitives[0]
  .extras.targetNames`) against the current file *first*. The avatar code
  binds gaze/gesture/lip-sync by name, not index -- a same-named rig from
  the same export pipeline drops in safely (confirmed identical between
  the two models in this branch's history); a differently-named rig will
  silently break body pose or facial blendshapes with no error at all.
- `narration/service.py`'s `SYSTEM_PROMPT` has one line carving out
  greetings/small-talk/thanks to get a brief natural reply with empty
  evidence. Without it, Gemini/Vertex narrates the day's readiness/sleep/HR
  numbers for literally any input, including "hey, hi" -- the rest of the
  prompt only ever talks about explaining wearable data, so that's what it
  defaults to. Don't delete that line as dead-looking boilerplate.
- If a teammate on the same branch/commit reports a different 3D model
  than you see: `model.glb` is tracked in git (not gitignored), lives at
  `frontend/public/assets/model.glb`, and is served to the browser from
  the *built* `frontend/dist/assets/model.glb` copy -- Vite copies
  `public/` verbatim with no content hash, so the URL never changes even
  when the file's bytes do. Check `git log -1 --format=%H` matches on both
  machines first (a stale checkout is the most likely cause); if commits
  already match, a hard-refresh or private window rules out a stale
  browser cache at that same unchanging URL.
- The avatar's procedural pose system (`Avatar.tsx`'s `damp()` calls in the
  `useFrame` loop) offsets FROM the GLB's own bind-pose rotation, captured
  once at load as `base[name]` -- it is not an absolute target. If a bone
  looks wrong in a given state, check whether that state actually offsets
  the bone far enough from the bind pose, not just whether an offset
  exists at all. The bind pose itself is a near-horizontal T-pose for
  every arm bone (verified identical between avatar model exports so far)
  -- don't assume it's already a relaxed standing pose.
- The remote face service on the SCC box (`/data/saurav/avatar_face_service`,
  `start.sh`, tmux session `avatar-face`, port 8765) is started with
  `exec uvicorn ...` -- `exec` replaces the shell in that tmux pane, so
  there is no shell left underneath it. Sending `C-c` to stop it kills the
  *entire pane/window/session*, not just the process -- tmux has nothing
  left to return a prompt on. To restart it: `tmux new-session -d -s
  avatar-face` fresh, then `send-keys -t avatar-face "bash
  /data/saurav/avatar_face_service/start.sh" Enter` -- do not try to reuse
  the old session after a C-c to this pane, it's already gone.
- SSH access to `scc` lands as user `nvidia`, not `saurav` (who owns
  `/data/saurav` and the actual running services) -- but `nvidia` has
  **passwordless sudo to any user** (`sudo -n -l` shows `(ALL)
  NOPASSWD: ALL`), confirmed working. `sudo -n -u saurav <cmd>` is the
  correct way to inspect/edit/restart anything under `/data/saurav`
  non-interactively; no password prompt, no need for `sudo -iu saurav`
  with a login shell (that combination is what disconnected an earlier
  attempt that bundled it with a port-forward command -- plain non-login
  `sudo -n -u saurav` avoids whatever the bastion didn't like about that).
- The SCC box's original `avatar_face_service` venv
  (`/data/saurav/envs/avatar_face_service`) is Python 3.14 -- too new for a
  stable PyTorch wheel as of 2026-09. Real ML work there runs in a
  separate venv, `/data/saurav/envs/avatar_face_lipsync`, built from the
  system's `/usr/bin/python3.12` instead (`nvcc`/CUDA toolkit isn't
  installed system-wide either, but that's fine -- PyTorch's own wheels
  bundle the CUDA runtime they need for inference; only building custom
  CUDA kernels from source would need `nvcc`). Torch was installed via
  `pip install torch --index-url https://download.pytorch.org/whl/cu124`
  (driver is 595.71, plenty new enough for cu124). `start.sh` now
  activates this venv, not the original one.
- `ffmpeg` and `espeak`/`espeak-ng` are now installed system-wide on the
  SCC box (`apt-get install -y ffmpeg espeak-ng espeak`, `nvidia` has
  passwordless root sudo so this needed no workaround). Only `ffmpeg` is
  actually used by anything running today -- see AGENTS.md's Log entry
  and the plan doc for why `espeak` is installed but unused (a
  `phonemizer` compatibility issue, not a missing package).
- HuggingFace Hub (`huggingface.co`) is reachable from the SCC box with no
  proxy/auth needed -- confirmed both a plain `curl` 200 and real model
  downloads (`facebook/wav2vec2-base-960h`, ~360MB) working.
- Body gestures (EMAGE, `services/avatar_body_service/`) run in their own
  venv, `/data/saurav/envs/emage` (Python 3.12) -- NOT the same venv as
  the face/lip-sync service (`avatar_face_lipsync`). EMAGE's model code
  is imported from a plain `git clone` of `PantoMatrix/PantoMatrix` at
  `/data/saurav/emage`, on `PYTHONPATH`, not a pip package. `transformers`
  is pinned to exactly `4.46.3` -- newer versions break EMAGE's
  `PreTrainedModel` subclass (`AttributeError:
  'EmageVQVAEConv' object has no attribute 'all_tied_weights_keys'`).
  tmux session `avatar-body`, port 8766, tunneled the same way as the
  face service's 8765.
- Retargeting SMPL-X (EMAGE's output skeleton) rotations onto this rig's
  Mixamo-style bones: negate the ENTIRE axis-angle vector
  (`[-x,-y,-z]`, not per-axis sign flips) before converting to a
  quaternion. Found empirically with a throwaway Three.js test harness,
  not derived analytically -- confirmed on two independent frames.
  Don't re-derive this from scratch if it needs revisiting; start from
  "try negating the whole vector first."
- Async WebSocket services that both receive a client stream AND emit
  their own independently-timed output (the body-gesture service is the
  first one to do this) must NOT emit from inside the same loop that's
  waiting on `websocket.receive()` -- input arrival rate and how fast
  you actually want to emit are unrelated, and coupling them means a
  client that sends few large bursts (confirmed: the browser's `fetch`
  stream for TTS audio does exactly this) will fill an output queue
  that never actually drains. Give input-receiving and output-emitting
  each their own `asyncio` task; this cost real debugging time to find
  (looked fine in a synthetic small-chunk test, broke against the real
  browser's chunking) -- test against how the real client actually
  sends data, not just a script mimicking it a different way.
- NVIDIA's CUDA/TensorRT apt repo
  (`developer.download.nvidia.com/compute/cuda/repos/ubuntu2204/x86_64`,
  added via the `cuda-keyring_1.1-1_all.deb` package) needs no NGC/dev-portal
  login -- it's a genuinely open distribution channel, separate from
  NGC container images and gated model downloads. `libnvinfer-dev` /
  `cuda-toolkit-12-9` are both installable from it directly. Packages
  from this repo cross-depend on EXACT matching versions across the
  whole chain (e.g. `libnvinfer-dev` also needs `libnvinfer-headers-dev`,
  `libnvinfer10` at the identical version) -- `apt-get install
  pkg=X.Y.Z` for just the one package you want will fail with unmet
  dependencies if apt already resolved a different version for a
  transitive dependency; list every related package pinned to the same
  version in one `apt-get install` command instead of installing them
  one at a time.
- TensorRT's `trtexec` CLI (needed by `NVIDIA/Audio2Face-3D-SDK`'s own
  `gen_test_data.py`/`gen_sample_data.py` scripts, and generally useful
  for any ONNX-to-TensorRT-engine conversion) comes from the separate
  `libnvinfer-bin` apt package, not `libnvinfer-dev` -- and even once
  installed, it lands at `/usr/src/tensorrt/bin/trtexec`, not anywhere
  on `PATH` by default. Add that directory to `PATH` explicitly.
- `NVIDIA/Audio2Face-3D-SDK`'s `CMakeLists.txt` requires zlib >=1.3.1;
  Ubuntu 24.04's system zlib is 1.3 -- one version-check line
  (`find_package(ZLIB 1.3.1 REQUIRED)` -> `1.3`), not a real
  incompatibility, confirmed by the subsequent build succeeding cleanly.
- The real, open (non-gated) `NVIDIA/Audio2Face-3D-SDK` builds and runs
  on the SCC H100 (verified: 147/147 CMake targets, real TensorRT engine
  conversion, real sample inference on real audio) but its output is
  NVIDIA's own proprietary per-character shape/vertex basis (their
  "mark"/"claire"/"james" reference meshes), confirmed by reading
  `network_info.json` and the model's HuggingFace README directly --
  NOT ARKit blendshape weights, despite that being how NVIDIA's own
  docs describe the separate, still-gated NIM microservice. There is
  no quick path from this SDK's output to our avatar's ARKit blendshapes
  without a real mesh-retargeting effort. Don't restart this build
  expecting a different answer; the blocker is the output format, not
  the environment setup (that part now works fine and is documented
  in docs/AVATAR_IMPLEMENTATION_PLAN.md).
- The two avatar GPU services (`avatar-face`, `avatar-body`) now have a
  watchdog on the SCC box, per explicit "keep it running always"
  request: `services/ensure_avatar_services.sh` (checks each service's
  `/health`, recreates its tmux session from scratch if it's not
  responding) runs via `saurav`'s crontab every 2 minutes and once at
  `@reboot` (after a 30s delay for drivers/networking). Logs to
  `/data/saurav/ensure_avatar_services.log`. This covers the box
  rebooting or a service process dying -- it does NOT cover the local
  SSH tunnels (8765/8766) from your own Mac to the box, which are a
  per-developer thing you still open yourself each session.

---

## Branch workflow

- BioTwin 2.0 work uses `biotwin2.0`, branched from `dev`, per Shivendra.
- Make logical verified commits as Shivendra; push to `origin/biotwin2.0`.
- Other work follows its explicitly requested branch; do not switch this task to dev.
- Fetch before synchronizing. Incorporate newer `main` changes into `dev` with a normal merge when needed; preserve existing branch history.
- Keep local secrets, personal data, dependencies, and build output out of commits.
