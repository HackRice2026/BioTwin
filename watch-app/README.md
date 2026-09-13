# BioTwin Live for Garmin Venu 2

This is a foreground Connect IQ watch app. Develop and build it on the Mac;
install the compiled app on the watch. It requests a delivery every five seconds
while open. Phone connectivity, request duration and Garmin's own measurement
cadence determine the actual latency. This does not mirror every screen in Garmin
Connect or provide continuous five-second delivery after the watch app closes.

## Pipeline

```text
Venu 2 sensors / device history
    → WatchStream.mc (timestamped samples, bounded retry queue)
    → Communications.makeWebRequest through the paired phone / Garmin Connect
    → HTTPS POST /api/ingest/watch (ingestion-only device token)
    → WatchBatch validation → normalize → Runtime.ingest → persistent frames
    → Runtime.compute → /ws/live → BioTwin dashboard and avatar
```

The Connections page creates/replaces/revokes a watch token. Only its hash is
stored on the server. The token expires in 90 days, only authorizes ingestion,
and cannot read an account, export data or act as a login session. Replacing the
token invalidates the old build; configure and rebuild the watch app afterwards.

## Measurements and limits

| Measurement | Watch API | Meaning and freshness |
| --- | --- | --- |
| Heart rate | `Sensor.enableSensorEvents`, with `ActivityMonitor.getHeartRateHistory` fallback | Fresh sensor events when reported; history retains its original timestamp and invalid samples are omitted |
| Steps | `ActivityMonitor.getInfo().steps` | Current daily total, checked every send tick |
| Calories | `ActivityMonitor.getInfo().calories` | Total daily calories including resting energy; **not active calories** |
| Distance | `ActivityMonitor.getInfo().distance` | Current daily total, converted from centimetres to metres |
| Floors | `ActivityMonitor.getInfo().floorsClimbed` | Current daily total, if reported |
| Garmin stress | `SensorHistory.getStressHistory` | Latest available history sample, not a new measurement on every poll |
| Body Battery | `SensorHistory.getBodyBatteryHistory` | Latest available Garmin estimate, distinct from charged/drained daily totals |
| Pulse Ox | `SensorHistory.getOxygenSaturationHistory` | Latest available sample; this app does not initiate a new oximetry measurement |
| Acceleration | `Sensor.registerSensorDataListener` | Newest XYZ magnitude, in milligravity including gravity; not inferred exertion |

Unavailable or out-of-range readings are omitted. History rows are sent separately
using their original measurement times. The dashboard shows each value's age,
so an old stress sample never becomes "live" just because heart rate arrived.
Sleep, HRV, respiration, training metrics and other Garmin Connect information
are not supplied by this app. Existing cloud/import paths remain necessary for
those data. Proprietary stress and Body Battery values are displayed separately
from BioTwin readiness; they are not substituted for missing sleep or HRV inputs.

Garmin's background timer has a minimum five-minute interval. No Background
permission or background service is requested by this foreground implementation.

## Build on the Mac

1. Install Garmin's Connect IQ SDK and install the **Venu 2** device profile in
   SDK Manager. Complete Garmin's license/account flow if requested.
2. Run BioTwin with its existing backend and sign in to your personal account.
   In **Connections → Venu 2 · Connect IQ**, create a pairing token.
3. Use an HTTPS backend address reachable by the phone. For local development,
   a configured HTTPS tunnel must forward to the backend. Keep the backend and
   tunnel running; if the tunnel address changes, rebuild with the new URL.
4. Copy `watch-app/.env.example` to `watch-app/.env`. Set `API_URL` to the full
   `https://your-host/api/ingest/watch` endpoint and `API_KEY` to your pairing token.
   `SEND_INTERVAL_SECONDS` defaults to 5 (allowed range 5–30).
5. From the repository root:

   ```sh
   bash watch-app/scripts/build.sh
   ```

The build script generates a private `source/ApiConfig.mc` and a signing key on
first use, then builds `watch-app/bin/BioTwin.prg` for `venu2`. The signing key,
configuration, `.env`, and all compiled output are gitignored. The compiled app
contains the ingestion token: keep the PRG private and revoke the token if it is
shared accidentally. Keep the signing key for future updates of this app.

## Verify in the simulator, then on hardware

Open the installed Connect IQ simulator, then run:

```sh
monkeydo watch-app/bin/BioTwin.prg venu2
```

Configure simulated heart-rate and history data using the simulator's sensor
menus. Use a separate test BioTwin account so simulator values cannot contaminate
your personal measurements. Confirm that the watch screen acknowledges sends,
the dashboard changes without a refresh, and the exported frames have
`garmin_ciq_live` provenance and the expected timestamps. Disable connectivity
and restore it to check that retained samples arrive once, without duplicates.

For real hardware, connect the Venu 2 by USB and use a compatible MTP file-transfer
tool on macOS to copy **the Venu 2 build** into `GARMIN/APPS/`. Disconnect USB,
launch **BioTwin Live**, and keep the paired phone connected with Garmin Connect
available. Verify an actual device delivery before claiming hardware support.

## Reliability behavior

Only one request is outstanding. A batch is acknowledged only when the server
returns HTTP 200 and `accepted + duplicates` equals the batch size. Failed batches
remain queued with backoff up to 60 seconds. Requests time out after 15 seconds.
The queue is checkpointed in watch storage and survives a normal restart. Changing
the endpoint or token discards the prior pairing's queued data to prevent sending
one account's readings into another account.

There are at most 20 samples in a request and 60 waiting samples. During a long
outage the oldest waiting samples are discarded; the watch screen reports the
overflow count. This finite queue is not a lossless activity recorder. One
protected in-flight batch is retained for retry. A 401 asks for re-pairing; a 422
requires checking the endpoint contract/watch clock rather than silently dropping
the rejected batch. Daily counters are snapshots, not increments.

## Verification completed in this workspace

- Backend tests cover partial rows, range and timestamp validation, all-or-nothing
  prevalidation, retry deduplication, corrections, token scope/rotation/expiry/
  revocation, account isolation/deletion, rate limiting, source precedence and
  WebSocket delivery.
- HTTP requests against a separate local test database persisted synthetic frames
  and recomputed the avatar pulse. A browser visibly changed from 84 to 91 bpm
  and from 5,432 to 5,447 steps without reloading, while old history ages remained.
- Generic Garmin compilation passed. This checks source compilation only.
  The **Venu 2 target build is blocked by the missing device profile**, and the
  simulator and physical-watch paths have **not** been verified. The ignored
  `BioTwin-generic.prg` uses compile-only configuration and must not be sideloaded.

## Sources and reference plumbing

The local reference checkout at `/private/tmp/medref` is
[Lutu-gl/Garmin-Meditation-App](https://github.com/Lutu-gl/Garmin-Meditation-App).
Its manifest structure, `makeWebRequest` options/callback idiom and guarded
heart-rate history read informed the transport. The meditation screens and
models were not imported. The config generator uses the same private-generated-
constants pattern, with URL validation and restrictive file permissions.

- [Garmin Sensor API](https://developer.garmin.com/connect-iq/api-docs/Toybox/Sensor.html)
- [Garmin SensorHistory API](https://developer.garmin.com/connect-iq/api-docs/Toybox/SensorHistory.html)
- [Garmin ActivityMonitor totals](https://developer.garmin.com/connect-iq/api-docs/Toybox/ActivityMonitor/Info.html)
- [Garmin background scheduling limits](https://developer.garmin.com/connect-iq/api-docs/Toybox/Background.html)

## Continuation prompt

> Finish Venu 2 hardware verification for BioTwin's existing watch-app/. Read this
> README and the current code before editing. Install the Venu 2 profile after
> the user completes Garmin's agreement/account flow. Use a separate test account
> and an HTTPS endpoint to build and run in the simulator. Prove accepted frames,
> original measurement times, retries, database persistence and browser updates.
> Then configure the user's intended BioTwin account and build a private Venu 2
> PRG for physical sideload. Verify actual hardware deliveries and measure latency
> before reporting success. Preserve unrelated MATLAB work and personal data;
> the user explicitly selected the existing mathworks branch for this work.
> Garmin's agreement has been accepted with permission; SDK Manager is waiting
> for Garmin account sign-in before device-profile installation.
