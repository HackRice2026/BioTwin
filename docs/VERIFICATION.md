# Verification record

The actual account integrations remain blocked by credentials. This file distinguishes exercised local behavior from live-device claims.

## Exercised

- The complete test run passed **32 Python tests and 2 frontend FSM tests**.
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

## External dependencies not exercised live

| Dependency | Why not | What proves completion |
|---|---|---|
| This user's Garmin watch/cloud API | No watch model, approved API credentials, or captured user export supplied | Consented measurement changes the personal avatar through the live adapter |
| Direct watch Bluetooth | No physical broadcast device attached to the browser | Actual watch Heart Rate Service notification reaches the store and socket |
| Google OAuth / Calendar | No configured client or consented test account | Read busy intervals and insert a reviewed event with the reminder on the user's calendar |
| ElevenLabs audio | No API key/voice account supplied | Real streaming audio plays from a grounded answer |
| Fitbit / Google Health | No Fitbit device, OAuth app, or registered subscriber supplied | Verified real notification is fetched, deduped, stored and rendered |
| Public HTTPS deployment | No domain/hosting choice supplied | Deploy configured container behind TLS and verify callbacks |

## Failure handling

The tested offline fallback is public synthetic replay, not personal data cached by a service worker. A PostgreSQL failure returns a visible error rather than moving personal writes to an unrelated local database. Garmin imports are functional even without live API access. An unavailable calendar does not generate supposedly verified slots. Missing ElevenLabs configuration gives a visible speech error while preserving text. Missing/invalid language-service output uses deterministic narration.

The supplied specification called for manually exercising every real external failure. That cannot be truthfully claimed without the actual integrations and devices. Local and protocol failure tests are evidence for the implementation, not a replacement for that final integration drill.
