# BioTwin 2.0 verification — 2026-09-12

## Connected calendar follow-up

- After merging concurrent watch/forecast updates: **99 Python tests passed,
  3 PostgreSQL-only cases skipped locally**; frontend's **21 tests**, production
  build, Ruff and schema checks pass.
- `scripts/calendar-check.mjs` verifies consent-return navigation, actual event
  titles/details, tasks, date/source/search filters, draft review, confirmed write
  request and agenda refresh, and clear partial/failure states at 1440/390/360px.
  Calendar provider responses are controlled test data; no real events are written.
- Backend tests exercise all calendar/event/task pagination, recurring instances,
  all-day end dates, missing Tasks permission, account isolation, conflicts,
  idempotent confirmation, DST gaps, and draft expiry/deleted-account protection.
- Real **Vertex gemini-2.5-flash** answered from fixture event facts and prepared
  a requested event at the correct local time. Its first reading attempt hit the
  existing numeric guard; supplying consistent readable date/time facts and
  avoiding unsolicited spelled-out counts corrected the live check.
- General navigation/PWA, conversation audio/failure/history, and account/FIT
  browser regressions also pass after the calendar change.
- No connected calendar account was present in this local database. Actual Google
  consent, calendar reads/writes and Tasks API access still need a connected account.
  Existing users may need renewed consent for `tasks.readonly`; setup is in
  [INTEGRATIONS.md](INTEGRATIONS.md#google-calendar-events-and-reminders).

## Verified in this redesign

- Python: **66 passed, 3 skipped** locally. The skipped cases require a dedicated
  PostgreSQL test database; CI supplies PostgreSQL. Ruff and generated-schema
  drift checks pass.
- Frontend: **14 unit tests**, production TypeScript/Vite build, question-topic
  priorities, split-word caption alignment and invalid timing rejection pass.
- Layouts: Chrome at **360, 390, 1024 and 1440 pixels**, all five navigation
  sections, persistent battery, no page errors or horizontal overflow.
- Browser flows: every topic panel, manual dismissal, all three simulation
  choices through the real simulation endpoint, calendar event/reminder request
  shape, account registration, original FIT import, personal signal rendering,
  account deletion and transcript history/replay.
- Voice regressions: real MediaRecorder with generated audio; six immediate
  topic routes before a delayed answer, actual browser audio decoding/playback,
  blocked-autoplay recovery, text retained on speech failure, clear answer-service
  failure, history reload and keyboard dismissal.
- PWA: standalone manifest, PNG/maskable icons, Apple touch icon, active service
  worker, public-only cache, offline reload and offline avatar/scenario rendering.
  Private API responses are not cached. The avatar GLB and the previously remote
  lighting HDRI now have content-versioned entries in the offline precache.

## Real recorded-question check

`scripts/redesign-voice-check.mjs` used a temporary account with generated
measurements and a spoken WAV supplied to Chrome's microphone capture device.
It exercised **MediaRecorder → real Vertex transcription → real Vertex
`gemini-2.5-flash` narration → real ElevenLabs George timed MP3 stream → browser
playback/captions → automatic Overview return → transcript reload**.

The steps panel appeared **60 ms** after the accepted question request and before
narration completed. The response used the recorded 7,100-step value. The browser
observed playing/ended events and changing highlighted caption words. The saved
answer returned after reload. A second complete run played a **25.94-second**
answer with **49 caption-word changes**, returned to Overview and restored its
transcript without browser errors. This is a real recorded-audio/provider test, not a
physical microphone or iPhone Safari test.

A separate longer real ElevenLabs stream confirmed that HTTP alignment timestamps
are absolute (successive segments started at 0, 0.917 and 5.004 seconds). Adding
chunk offsets would double-count elapsed time; the implementation and regression
test now explicitly prevent that.

## Limits and dependencies

- Physical iPhone microphone permission/capture and Add to Home Screen were not
  manually exercised. Browser microphone capture requires HTTPS on a LAN phone
  URL; localhost is a secure-context exception. Manifest/icons/service worker
  and standalone metadata were verified programmatically.
- Calendar UI requests/reminders were verified against intercepted provider
  responses to avoid creating real events. Existing backend calendar conflict,
  idempotency and provider-protocol tests remain. Real Google/Outlook OAuth was
  not repeated by this redesign.
- Live watch capture was not repeated. All existing cloud/import/browser BLE/
  local companion controls remain, with the same backend routes. Connections
  stays mounted across tab navigation so browser Bluetooth remains connected.
- Avatar face/body integrations remain. During this session the local default
  ports did not identify the expected GPU services: 8765 returned HTTP 426 and
  8766 identified `jarvis-agent`. Therefore live GPU face/body inference is not
  claimed here. Procedural/avatar conversation states and audio playback work.
- No public deployment was made. Keys, recorded test audio, screenshots and
  temporary test databases remain outside git. The existing Three.js bundle
  size warning remains; build succeeds.

## Reproduce

Build the frontend and start the API, preferably with a dedicated test database.
Set `BIOTWIN_TEST_URL` when using a port other than 8000. Standard browser checks
use intercepted speech and must run against a server with external narration
disabled; CI does this naturally without credentials.

```sh
uv run pytest -q
uv run ruff check core ingestion modeling narration shared tests scripts
npm run test --prefix frontend
bash scripts/check_schema.sh
npm run build --prefix frontend
node scripts/browser-check.mjs
node scripts/voice-check.mjs
node scripts/account-check.mjs
# Explicitly calls real configured providers; WAV should ask about steps:
BIOTWIN_QUESTION_WAV=/path/to/question.wav node scripts/redesign-voice-check.mjs
```

Evidence files are generated in ignored `test-results/`. Do not infer hardware or
external-service verification from mocked protocol tests.
