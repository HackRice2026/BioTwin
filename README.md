# BioTwin

A working Garmin-first wearable recovery app: an articulated 3D twin, physiological charts, personal recovery fitting, daily planning, Google Calendar events and reminders, and ElevenLabs speech.

The default workspace is an explicitly **synthetic demo**. Your own account starts empty. Real measurements never get supplemented with synthetic readings.

## Run locally

Requires Python 3.12+, [uv](https://docs.astral.sh/uv/), and Node 22+.

```sh
uv sync --frozen
npm ci --prefix frontend
uv run python -m scripts.setup
npm run build --prefix frontend
uv run uvicorn core.api:app --host 0.0.0.0 --port 8000 --no-access-log
```

Open **http://localhost:8000**. For frontend hot reload, run `bash scripts/dev.sh` and open http://localhost:5173. Offline installation must be tested using the production build on port 8000.

### LAN access (share your dev server with a teammate)

Both dev servers listen on `0.0.0.0` by default, so anyone on the same WiFi can reach them at your machine's LAN IP instead of `localhost`. Find that IP:

```sh
# macOS
ipconfig getifaddr en0
# Linux
hostname -I
# Windows (PowerShell)
ipconfig
```

Then set `LAN_ORIGIN` in `.env` to that address with the frontend's port, e.g. `LAN_ORIGIN=http://192.168.1.23:5173`, and restart `bash scripts/dev.sh` (or the production server) so the backend accepts it. A teammate on the same WiFi opens `http://192.168.1.23:5173` in their browser — voice, live updates and API calls all work the same as on `localhost`. They need no Google or ElevenLabs setup of their own: narration and speech are server-side, so your host machine's credentials cover every LAN visitor (see docs/INTEGRATIONS.md for the per-machine setup, which is only needed for a separate copy of the app). Without `LAN_ORIGIN` set, requests from anything but `localhost`/`127.0.0.1` are rejected (CORS, the `/ws/live` WebSocket, and the POST/PUT/DELETE origin check all enforce it).

Create an adult account from “Connect your own story.” In Connections, import an original Garmin `.FIT` activity or a supported JSON export. `.FIT` activities provide recorded heart rate; they do not necessarily contain sleep or RMSSD HRV. Missing signals stay missing and reduce readiness confidence.

## Features

- One ingestion pipeline for Garmin, Google Health/Fitbit, FIT/JSON imports, recorded replay, synthetic scenarios, and optional Bluetooth heart-rate broadcast.
- Durable, idempotent measurement storage; UTC event time; source disagreement; explicit quality and missingness; authenticated WebSocket snapshots with resume, heartbeat and bounded queues.
- Weighted robust personal baselines, daily observation shrinkage, six readiness states with hysteresis, automatic recovery segmentation, nonlinear time-constant fitting, and held-out session errors.
- Predictions stored before their observations; the original forecast is immutable. Scoring is a separate derived artifact.
- Original locally stored 3D human: articulated arms, hands, fingers, legs, feet and head; breathing/pulse from fresh measurements; continuously blended posture; exercise and recovery state machine. Auto/Low/Medium/High graphics and reduced motion.
- Heart rate, RMSSD, sleep stages, respiration, resting HR, oxygen saturation, steps, readiness history, and recovery graphs with provenance.
- Calendar-feasible nap/workout suggestions, a clearly marked experimental day outlook, calendar event creation and popup reminders. Availability is rechecked before each write; repeat submissions do not duplicate an event.
- Typed or spoken questions answered by Gemini from the computed NarrationContext, with evidence and numerical validation. ElevenLabs speech plays automatically with avatar gestures; saved transcripts survive reloads and support replay. Explicit text fallbacks handle either provider failing.
- Rest / light activity / exercise simulation on the same avatar and charts.
- Installable PWA with a production-generated synthetic offline bundle. Service workers cache the app and public demo only, never personal API responses.
- Adult accounts, password hashing, opaque HttpOnly sessions, per-user envelope-encrypted provider tokens, export and deletion, configurable measurement retention, diagnostics, Docker deployment, and CI.

## Real integrations need setup

A Garmin watch paired to an iPhone is not a developer API credential. Garmin cloud data becomes accessible after the watch syncs to Garmin Connect and requires an approved developer integration. A compatible watch can additionally broadcast heart rate directly to a supported desktop Bluetooth browser; this is a separate heart-rate-only path.

Fill in the ignored `.env` file using [the integration guide](docs/INTEGRATIONS.md):

| Integration | Needed | Current behavior without it |
|---|---|---|
| Garmin cloud | Approved Connect Developer access, client ID/secret, configured webhook | FIT/JSON imports and supported Bluetooth broadcast remain available |
| Fitbit / Google Health | OAuth client, enabled API, test users/approval, webhook setup | Clear setup error; no invented live data |
| Google Calendar | Google OAuth client and Calendar API enabled | Calendar proposals remain unavailable for real accounts |
| Gemini | API key, narration endpoint/model, and external narration enabled | Clearly labeled deterministic context explanation |
| ElevenLabs | API key and accessible voice ID | Grounded text works; speech reports setup required |

Gemini and ElevenLabs were exercised together in Chrome using a temporary account with generated test measurements: an answer was saved, spoken, and restored after reload. The current local voice is **George**, selected with user approval after the original library voice required a paid plan. **Live Garmin cloud sync and real Google Calendar consent/writes still require verification.**

## Team accounts

Not everyone on the team has the paired Garmin watch/account, so a new teammate's login starts empty. `scripts/onboard_teammate.py` gives them their own account seeded with a replay copy of the `demo` account's current history (real, live-synced Garmin/InfluxDB data when `DEMO_USES_REAL_DATA=true`) instead of a blank dashboard:

```bash
PYTHONPATH=. uv run scripts/onboard_teammate.py --email teammate@example.com --name Teammate
```

Prints the generated password once (pass `--password` to set your own). Safe to re-run for the same email later to refresh their data with the source account's latest history -- it only ever writes to that one teammate's own rows, tagged `provenance: replay`, never touching anyone else's account.

## Verification

For the foreground Venu 2 app, device pairing, five-second delivery target,
measurement limits and hardware verification status, see the
[watch app setup guide](watch-app/README.md).

```sh
uv run pytest -q
npm run test --prefix frontend
bash scripts/check_schema.sh
npm run build --prefix frontend
# With the app running and Chrome installed on macOS:
node scripts/browser-check.mjs
node scripts/account-check.mjs
node scripts/voice-check.mjs
# Optional live provider test using the configured local keys:
BIOTWIN_LIVE_VOICE=true node scripts/voice-check.mjs
node scripts/performance-check.mjs
```

For PostgreSQL contract tests, set `TEST_POSTGRES_URL` to a dedicated test database. CI runs the suite against both SQLite and PostgreSQL. For Linux browser tests, install Playwright Chromium and set `BIOTWIN_TEST_BUNDLED_CHROMIUM=true`.

See [verification evidence and limits](docs/VERIFICATION.md), [architecture](docs/ARCHITECTURE.md), [model assumptions](docs/MODEL_CARD.md), and [asset licenses](docs/LICENSES.md).

## Production deployment

The container serves the compiled frontend and FastAPI from one origin. Configure `.env`, set `POSTGRES_PASSWORD`, and run:

```sh
docker compose --env-file .env -f ops/docker-compose.yml up --build -d
```

Terminate TLS with the provided Caddy example or your host's proxy. Set `PUBLIC_URL` and `FRONTEND_ORIGIN` to the same HTTPS site URL and `COOKIE_SECURE=true`. Keep **one API worker** for the in-process WebSocket fan-out; horizontal scaling requires a shared broker. Database credentials and provider tokens must not be committed. No public deployment is created automatically.
