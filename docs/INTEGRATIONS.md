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

Connect from BioTwin. Scopes are `calendar.readonly`, `calendar.events`, and `tasks.readonly`. Enable the Google Tasks API too if Tasks should appear. Existing connections can reconnect to grant the additional Tasks scope; declining it does not hide calendar events. The primary calendar timezone is read after consent, and the app opens Daily plan. The agenda fetches every provider page across all readable Google calendars in the displayed 7- or 30-day range, with recurring instances expanded. FreeBusy remains authoritative for conflicts.

Daily plan now shows named events, all-day entries, details/links and task lists, with date navigation, search and calendar/task filters. It refreshes after connecting/adding, on window focus, and every minute while visible. Changing the date range exposes earlier or later events; there is no first-page event cutoff.

Ask the twin about the displayed calendar, or ask it to add an event with a title, date and time. Vertex/Gemini receives only the supplied calendar facts alongside the existing wearable context. New events appear as editable drafts. The review panel's **Add to calendar** button performs the write; a draft alone never books. **New event** also works without Gemini. The selected writable Google calendar is checked for conflicts, the event includes the reviewed reminder, and stable provider IDs prevent duplicate retries. No attendees or invitations are added. Drafts expire after an hour. Planner-generated wellness proposals retain their existing modeling constraints.

Daily plan → choose the reminder lead time → click the arrow on a proposal. The server requires an authentic stored proposal, rechecks current model constraints and calendar availability, then inserts an idempotently identified event in the primary calendar. It includes one popup reminder. No attendees are added and no invitations are sent. Clinical data and readiness values are not placed into the calendar description. Google Calendar and device settings control delivery of the reminder; BioTwin does not claim it can guarantee a notification on a sleeping phone.

The server supports multiple calendar IDs through profile settings (`calendar_ids`); the default is `primary`. It refuses to present an empty, verified schedule if a selected calendar returns an error.

References: [Create events](https://developers.google.com/workspace/calendar/api/guides/create-events), [Reminders and notifications](https://developers.google.com/workspace/calendar/api/concepts/reminders), [Incremental synchronization](https://developers.google.com/workspace/calendar/api/guides/sync).

Agenda references: [Calendar list](https://developers.google.com/workspace/calendar/api/v3/reference/calendarList/list), [Expanded event listing](https://developers.google.com/workspace/calendar/api/v3/reference/events/list), [Tasks listing](https://developers.google.com/workspace/tasks/reference/rest/v1/tasks/list), [Tasks scopes](https://developers.google.com/workspace/tasks/auth).

## Outlook Calendar, events and reminders

`TODO(blocked): Azure app registration, enabled Microsoft Graph calendar permissions and user consent -- configure client credentials and redirect URI.`

Register an app in the [Azure Portal App registrations](https://portal.azure.com) blade (any Microsoft account, personal or work/school, can register one), add `${PUBLIC_URL}/auth/microsoft-calendar/callback` as a web redirect URI, and create a client secret under Certificates & secrets. Configure:

```dotenv
MICROSOFT_CLIENT_ID=...
MICROSOFT_CLIENT_SECRET=...
```

Connect from BioTwin. Scopes are `Calendars.ReadWrite` and `offline_access` (Microsoft's identity platform issues a refresh token because of the scope, not a separate `access_type=offline` parameter the way Google needs). Busy time is read via `/me/calendarView`, filtered to events with `showAs` of `busy` or `oof`; free/tentative/working-elsewhere entries on the calendar do not block a slot. If both Google and Outlook are connected, availability merges busy time from both -- a meeting on either calendar counts. New events are still written to Google when both are connected; Outlook is the target only when Google isn't.

Unlike Google, Graph does not accept a client-chosen event ID for idempotent creation; a local id-to-event mapping (`calendar_event_ref`) plays that role instead so a retried request cannot double-book. Unlike Google, Graph's event `start`/`end` want a local, offset-free clock time paired with an explicit IANA `timeZone` field, not an offset-inclusive timestamp -- the request is built accordingly. The primary calendar's timezone is deliberately not auto-detected after connecting the way it is for Google: Graph's `mailboxSettings.timeZone` comes back as a Windows timezone name ("Pacific Standard Time"), not IANA, and saving that into the profile would break every other `ZoneInfo(...)` call in the app rather than just leaving the existing zone alone. Set the profile timezone directly, or connect Google Calendar too, if that auto-detection matters.

Disconnecting removes the locally stored token only. Microsoft's identity platform has no per-app token-revoke endpoint the way Google's `/revoke` is -- `/me/revokeSignInSessions` revokes every session for every app, the wrong scope for "disconnect this one integration" -- so the token is simply forgotten and left to expire.

References: [Get calendarView](https://learn.microsoft.com/en-us/graph/api/calendar-list-calendarview), [Create event](https://learn.microsoft.com/en-us/graph/api/calendar-post-events), [Register an app](https://learn.microsoft.com/en-us/entra/identity-platform/quickstart-register-app).

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

### Vertex AI instead of an AI Studio key

An AI Studio `NARRATION_API_KEY` bills through a separate prepay-credits
balance that can deplete while the project's ordinary Cloud Billing is
perfectly healthy, which surfaces as `429 RESOURCE_EXHAUSTED`. Vertex AI bills
through normal Cloud Billing instead, so it keeps working when that is the
problem. Setting it up, once per machine that runs the server:

```bash
brew install google-cloud-sdk                 # Mac; any gcloud install works
gcloud auth application-default login         # log in with the account that owns the project
gcloud services enable aiplatform.googleapis.com --project=<your-project-id>
```

Find the project ID in the Cloud Console project switcher at the top of
[console.cloud.google.com](https://console.cloud.google.com). Then in `.env`:

```dotenv
USE_VERTEX_NARRATION=true
ALLOW_EXTERNAL_NARRATION=true
VERTEX_PROJECT_ID=<your-project-id>
```

Restart the server. Ask the twin anything: `mode` of `language_service` and a
`model` starting with `vertex:` confirms it, where the template fallback means
it is not working.

If `gcloud services enable` fails with `PERMISSION_DENIED`, the logged-in
account does not own that project -- a project AI Studio auto-created for a key
often belongs to a different identity. Log in again as the owner. `VERTEX_REGION`
(`us-central1`) and `VERTEX_MODEL` (`gemini-2.5-flash`) rarely need changing,
and an AI Studio model name does not necessarily exist on Vertex:
`gemini-2.0-flash` 404s there. `gcloud auth application-default login` writes no
downloadable key file -- credentials land in `~/.config/gcloud/`, outside the
repository -- which also sidesteps orgs that block service-account key creation.

**Someone using your running server over the LAN link needs none of this.**
Narration is server-side: `google.auth.default()` resolves credentials in the
server process and the browser never calls Gemini, so the credential on the
host machine already covers every LAN visitor. The steps above are only for
someone standing up their own separate copy. Full rationale and the
per-machine verification log are in AGENTS.md, Section 7.

References: [Gemini OpenAI-compatible REST and structured responses](https://ai.google.dev/gemini-api/docs/openai), [Gemini models](https://ai.google.dev/gemini-api/docs/models), [Gemini audio transcription](https://ai.google.dev/gemini-api/docs/audio), [ElevenLabs streaming speech](https://elevenlabs.io/docs/api-reference/text-to-speech/stream).

## Optional Fitbit / Google Health

Enable Google Health API and configure `${PUBLIC_URL}/auth/fitbit/callback` using the same Google OAuth client. Scopes are limited to read-only activity/fitness, sleep, and health metrics/measurements. The implementation was checked against the current [v4 discovery schema](https://health.googleapis.com/$discovery/rest?version=v4).

Set `GOOGLE_WEBHOOK_SECRET` and create an HTTPS Google Health subscriber for `${PUBLIC_URL}/webhooks/google-health`. Configure its endpoint authorization as `Bearer <GOOGLE_WEBHOOK_SECRET>` and automatic subscriptions for the supported data types. Subscriber registration is an operator action in the Google project, not something performed with a consumer's wearable token.

The receiver implements Google's authorized/unauthorized verification handshake, requires the bearer secret, then verifies the actual webhook body's rotating Tink ECDSA signature against Google's public keyset. The durable worker maps `healthUserId` to the consenting account and fetches the notification's changed metric. Unsupported data types are not silently treated as physiological signals. Deletion events target the corresponding metric and interval/record.

`TODO(blocked): Google Health API OAuth consent and subscriber registration — complete configuration and verify with a real Fitbit measurement before claiming live Fitbit support.`

References: [Google Health endpoints](https://developers.google.com/health/endpoints), [Webhook subscriptions and signature verification](https://developers.google.com/health/webhooks).
