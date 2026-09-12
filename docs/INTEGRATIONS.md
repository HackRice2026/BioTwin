# Integration setup

The user's final requirements are Garmin first (watch paired with iPhone), minimum achievable latency, calendar writes with reminders, and ElevenLabs speech. Fitbit remains an optional adapter. Garmin recorded-data fallback is accepted. Gemini and ElevenLabs credentials are configured in the ignored local `.env`; wearable developer credentials remain outstanding.

## Local environment

Run `uv run python -m scripts.setup`. This creates a mode-0600 `.env` with a random token-encryption key and empty provider credentials. It preserves an existing file and prints no secrets. Restart the API after editing `.env`.

The encryption key must remain stable: rotating it without re-encrypting existing token envelopes makes those tokens unreadable. Reconnect accounts after such a rotation. Use your deployment secret manager in production.

## Garmin watch and iPhone

### Recorded import, available now

1. Sync the watch using Garmin Connect on the iPhone.
2. Open Garmin Connect on the web and export the **original FIT activity** for an activity with heart-rate recording.
3. Create a BioTwin account and choose Connections → Import Garmin data.
4. Import `.fit`, an array of normalized frames, or a JSON object with `frames`, `dailies`, or `sleeps`.

FIT import validates CRC and reads timestamped heart-rate records. Sleep, daily resting HR, and HRV may need separate exports. A proprietary stress/readiness/body-battery score or SDNN is never mapped into RMSSD. The included `fixtures/golden/generated-recovery.fit` is a generated test fixture, not a person's recording.

Normalized JSON example (use actual recorded values and timestamps):

```json
{"frames":[{"event_time":"2026-09-11T12:00:00Z","heart_rate_bpm":70,"resting_hr_bpm":61,"hrv_rmssd_ms":48,"respiration_brpm":14,"spo2_pct":98}]}
```

All file data is marked recorded/replay. Requests cannot choose another account's `user_id` or claim a live provenance. File upload limit: 20 MB; JSON limit: 100,000 records per import. Large exports can be split into multiple imports; duplicate samples are suppressed.

### Direct heart-rate broadcasting

If the watch supports standard Bluetooth Heart Rate Service broadcasting, enable its broadcast mode and choose **Connect heart-rate broadcast** in BioTwin using a supporting desktop Chromium browser. Keep Connections open. The browser sends timestamped measured BPM through the same normalizer/store/model/WebSocket path. Neither HRV nor breathing is inferred from Bluetooth BPM.

The app feature-detects `navigator.bluetooth`. When unavailable (including iPhone Safari), it explains that limitation and offers recorded imports. Whether the user's particular watch supports Bluetooth broadcasting is still unknown; the watch model was not supplied. Garmin mobile SDK live sensor streaming is not supplied by an iPhone PWA and requires a separate native integration.

### Approved Garmin cloud API

`TODO(blocked): Garmin Connect Developer Program approval, client ID/secret, and partner-specific delivery configuration — supply approved credentials and configure an HTTPS callback.`

Set:

```dotenv
GARMIN_CLIENT_ID=...
GARMIN_CLIENT_SECRET=...
GARMIN_WEBHOOK_SECRET=...
```

Register `${PUBLIC_URL}/auth/garmin/callback` as the OAuth redirect and configure the partner webhook to POST to `${PUBLIC_URL}/webhooks/garmin` with `Authorization: Bearer <GARMIN_WEBHOOK_SECRET>`. The receiver fails closed when that authorization is absent. If the approved partner setup requires another authentication mechanism, update and verify this boundary against the supplied partner documentation before enabling live delivery; the private delivery contract was not available here.

OAuth uses Garmin's PKCE authorization and token endpoints, stores a stable Garmin user-ID mapping, refreshes tokens before expiry, and calls the official registration deletion endpoint on disconnect. Health API daily/sleep pull uses upload-time windows; push payloads and allowlisted ping callback URLs enter the durable queue. No arbitrary callback host or redirect is followed with credentials.

Cloud notifications mean “data uploaded,” not a guaranteed per-heartbeat stream. BioTwin publishes after each committed measurement. The device → phone → vendor delay is outside its control. Overnight metrics cannot be honestly presented as live respiratory/HRV samples.

Primary references: [Garmin Health API](https://developer.garmin.com/gc-developer-program/health-api/), [Connect Developer overview](https://developer.garmin.com/gc-developer-program/overview/), [Garmin OAuth2 PKCE specification](https://developerportal.garmin.com/sites/default/files/OAuth2PKCE.pdf).

## Google Calendar, events and reminders

`TODO(blocked): Google Cloud OAuth client, enabled Calendar API and user consent — configure client credentials, redirect URI and test users.`

Enable Google Calendar API, create a web OAuth client, and add `${PUBLIC_URL}/auth/google-calendar/callback` as an authorized redirect. During unverified testing, allowlist each account in the consent screen's test users. Configure:

```dotenv
GOOGLE_CLIENT_ID=...
GOOGLE_CLIENT_SECRET=...
```

Connect from BioTwin. Scopes are `calendar.readonly` and `calendar.events`: the second scope implements the user's explicit event/reminder requirement. The primary calendar timezone is read after consent. The event cache uses incremental sync tokens; a 410 response discards the sync token and refetches. FreeBusy remains authoritative for conflicts.

Daily plan → choose the reminder lead time → click the arrow on a proposal. The server requires an authentic stored proposal, rechecks current model constraints and calendar availability, then inserts an idempotently identified event in the primary calendar. It includes one popup reminder. No attendees are added and no invitations are sent. Clinical data and readiness values are not placed into the calendar description. Google Calendar and device settings control delivery of the reminder; BioTwin does not claim it can guarantee a notification on a sleeping phone.

The server supports multiple calendar IDs through profile settings (`calendar_ids`); the default is `primary`. It refuses to present an empty, verified schedule if a selected calendar returns an error.

References: [Create events](https://developers.google.com/workspace/calendar/api/guides/create-events), [Reminders and notifications](https://developers.google.com/workspace/calendar/api/concepts/reminders), [Incremental synchronization](https://developers.google.com/workspace/calendar/api/guides/sync).

## Talk to your twin: Gemini and ElevenLabs

The local configuration has been verified with this Gemini client endpoint and model:

```dotenv
NARRATION_URL=https://generativelanguage.googleapis.com/v1beta/openai/chat/completions
NARRATION_API_KEY=...
NARRATION_MODEL=gemini-3.1-flash-lite
ALLOW_EXTERNAL_NARRATION=true
ELEVENLABS_API_KEY=...
ELEVENLABS_VOICE_ID=JBFqnCBsd6RMkjVDRZzb
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
```

`JBFqnCBsd6RMkjVDRZzb` is George, tested successfully and selected with the user's approval. The originally configured library voice returned `paid_plan_required`. The key can synthesize speech but cannot list voices (`voices_read` is absent); listing voices is not required for playback. A Gemini model-discovery request verified the selected model is available, and the actual chat-completions request returned a validated answer. The client uses low reasoning effort and structured JSON responses through Google's OpenAI-compatible REST endpoint.

Open **Talk to my twin**, type a question and send it, or press the microphone button and speak. Browsers with speech recognition submit the final transcription automatically. Otherwise, BioTwin records through MediaRecorder: tap the microphone again to finish, or it stops after thirty seconds. The recording is sent to the authenticated `/api/twin/transcribe` endpoint, and Gemini transcribes only the question before the normal narration flow starts. Recordings are limited to 5 MB and are not stored in the transcript. Gemini receives only the question and the computed context: readiness and contributions, baseline summary, facts about recorded signals, provenance and quality, trend, stored plan, and stored prediction. No provider tokens, account credentials, raw history query, or external tools are available to Gemini. Its answer must cite context evidence and pass the numerical/claim guard before reaching the UI or speech service. Failed requests or rejected output return a visibly labeled context fallback.

ElevenLabs automatically reads the accepted answer. Browser playback events animate the twin; a compact twin remains visible inside the conversation on mobile. Chrome streams MP3 as it arrives; unsupported MediaSource browsers buffer audio before playing. If autoplay is blocked, **Listen with ElevenLabs** resumes the in-memory audio after a user gesture. **Stop speaking**, closing the panel, and account changes stop playback. An audio error remains visible with the saved text and a retry action.

Each exchange is saved in the SQL `conversations` table before playback, including the question, accepted Gemini text, displayed response, provider mode/model, timestamp, and context snapshot. Reopening the panel or reloading restores history; older history is paginated. Transcript speech replay uses a new short-lived, owner-scoped ticket. User transcripts are included in data export and deletion and follow the configured retention period. Demo visitors have isolated browser-owned transcripts. Public offline example answers are explicitly not saved as personal exchanges.

No API key is sent to the browser. The server refuses narration endpoints outside the configured Google API host/path. Microphone capture needs browser permission. The built-in speech-recognition path and the MediaRecorder fallback are independently exercised by browser tests using simulated speech/streams. The native Gemini audio endpoint also transcribed a generated spoken question live. Physical microphone capture on this user's iPhone has not been exercised.

References: [Gemini OpenAI-compatible REST and structured responses](https://ai.google.dev/gemini-api/docs/openai), [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini audio transcription](https://ai.google.dev/gemini-api/docs/audio), [ElevenLabs streaming speech](https://elevenlabs.io/docs/api-reference/text-to-speech/stream).

## Optional Fitbit / Google Health

Enable Google Health API and configure `${PUBLIC_URL}/auth/fitbit/callback` using the same Google OAuth client. Scopes are limited to read-only activity/fitness, sleep, and health metrics/measurements. The implementation was checked against the current [v4 discovery schema](https://health.googleapis.com/$discovery/rest?version=v4).

Set `GOOGLE_WEBHOOK_SECRET` and create an HTTPS Google Health subscriber for `${PUBLIC_URL}/webhooks/google-health`. Configure its endpoint authorization as `Bearer <GOOGLE_WEBHOOK_SECRET>` and automatic subscriptions for the supported data types. Subscriber registration is an operator action in the Google project, not something performed with a consumer's wearable token.

The receiver implements Google's authorized/unauthorized verification handshake, requires the bearer secret, then verifies the actual webhook body's rotating Tink ECDSA signature against Google's public keyset. The durable worker maps `healthUserId` to the consenting account and fetches the notification's changed metric. Unsupported data types are not silently treated as physiological signals. Deletion events target the corresponding metric and interval/record.

`TODO(blocked): Google Health API OAuth consent and subscriber registration — complete configuration and verify with a real Fitbit measurement before claiming live Fitbit support.`

References: [Google Health endpoints](https://developers.google.com/health/endpoints), [Webhook subscriptions and signature verification](https://developers.google.com/health/webhooks).
