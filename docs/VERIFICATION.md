# Verification record

Gemini and ElevenLabs have been exercised live. Wearable cloud and Google Calendar account integrations still require credentials. This file distinguishes tested behavior from live-device claims.

## Exercised

- The complete test run passed **63 Python tests and 2 frontend FSM tests**.
- Python tests: normalizer validation, timezone-equivalent dedupe, missing signals, baseline day weighting, conflicting-source visibility, stale respiratory drivers, readiness dwell, planted-tau recovery, held-out error, future-only prediction scoring, and property-based planner constraints.
- Account/API tests: adult registration, authentication, account isolation, authenticated WebSocket delivery, client user-ID spoof resistance, Bluetooth ingestion, duplicate imports, late data, source setup errors, narration grounding, cross-origin mutation rejection, deletion, and bounded snapshots.
- Integration protocol tests: Google RMSSD vs SDNN parsing, Garmin daily/sample mapping, actual FIT decoding and CRC rejection, envelope encryption, Google ECDSA webhook signature verification, calendar conflicts/idempotent IDs/reminder payloads, and ElevenLabs request/stream behavior using a mocked service.
- Storage: concurrent duplicate commits and immutable predictions tested against **both SQLite and a locally started PostgreSQL 17 container**. Deletion of one user from a mixed webhook batch preserves the other user's records.
- Frontend FSM: full exercise → fatigue → recovery → restored traversal, dwell behavior, and renewed activity during recovery.
- Production frontend build and regenerated-contract drift check.
- Real Chrome desktop and 390px mobile rendering, navigation, what-if scenario, chat response, full reload offline with the GLB and precomputed what-if scenarios available, and no horizontal overflow. Browser evidence is generated in ignored `test-results/`.
- Real Chrome account creation, original FIT-file import, personal signals rendering, and account deletion.
- The production Docker image built successfully and served a populated synthetic snapshot and ready health endpoint.
- A 60-second active exercise simulation at 1440px desktop width recorded **p95 16.7 ms** frame intervals, p99 16.8 ms, approximately 60 fps, on this development machine. This is not a measured iPhone result.

## Voice and transcript verification

- Actual Gemini `gemini-3.1-flash-lite` answers and ElevenLabs George MP3 speech were exercised together in Chrome using an isolated temporary account with a generated recorded measurement. The browser observed real `playing` and `ended` audio events, and the avatar's speaking state was displayed.
- Reload restored the question, response, and timestamp. A simulated browser transcription submitted a second question through Gemini, persistence, ElevenLabs, and playback. This verifies the spoken-input application path, not physical microphone capture or accuracy on an iPhone.
- Browser checks exercised successful playback, transcript restore, blocked-autoplay recovery with Listen, a visible speech-service failure with text retained, and an unavailable ask endpoint. Standard CI uses generated audio and mocked provider availability; live checks require explicit `BIOTWIN_LIVE_VOICE=true`.
- Provider tests cover invented digits and spelled-out quantities, unsupported clinical claims, malformed/truncated answers, invalid evidence, timeout/rate-limit failures, and blocking requests to a foreign narration host.
- Conversation tests cover persisted Gemini text/context, duplicate request IDs, history pagination, retention, cross-account access, demo visitor isolation, export/deletion, replay tickets, and ElevenLabs empty/error/timeout responses.
- The direct-recording fallback was exercised with a real browser MediaRecorder and a generated audio stream. A generated spoken question was also successfully transcribed by the live Gemini audio endpoint. Physical microphone permission and capture on the user’s device remain untested.
- The configured library voice failed with HTTP 402; George succeeded after the user approved that change. Keys and generated audio remain outside Git.

## External dependencies not exercised live

| Dependency | Why not | What proves completion |
|---|---|---|
| This user's Garmin watch/cloud API | No watch model, approved API credentials, or captured user export supplied | Consented measurement changes the personal avatar through the live adapter |
| Direct watch Bluetooth | No physical broadcast device attached to the browser | Actual watch Heart Rate Service notification reaches the store and socket |
| Google OAuth / Calendar | No configured client or consented test account | Read busy intervals and insert a reviewed event with the reminder on the user's calendar |
| Fitbit / Google Health | No Fitbit device, OAuth app, or registered subscriber supplied | Verified real notification is fetched, deduped, stored and rendered |
| Public HTTPS deployment | No domain/hosting choice supplied | Deploy configured container behind TLS and verify callbacks |

## Failure handling

The tested offline fallback is public synthetic replay, not personal data cached by a service worker. A PostgreSQL failure returns a visible error rather than moving personal writes to an unrelated local database. Garmin imports are functional even without live API access. An unavailable calendar does not generate supposedly verified slots. Missing ElevenLabs configuration gives a visible speech error while preserving text. Missing/invalid language-service output uses deterministic narration.

The supplied specification called for manually exercising every real external failure. That cannot be truthfully claimed without the actual integrations and devices. Local and protocol failure tests are evidence for the implementation, not a replacement for that final integration drill.
