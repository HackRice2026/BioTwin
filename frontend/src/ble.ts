import { useEffect, useRef, useState } from "react";
import { post } from "./api";

/** Decode a Heart Rate Measurement (characteristic 0x2A37).
 *
 * Reading only the rate discards the two fields that matter most for a wearable:
 * the beat-to-beat intervals RMSSD is computed from, and the contact bits that
 * say whether the sensor is on the body. Field order is fixed by the
 * specification, so every optional field ahead of the intervals has to be
 * stepped over to find them.
 */
export function readHeartRate(view: DataView) {
  const flags = view.getUint8(0);
  let offset = 1;
  const hr = flags & 0x01 ? view.getUint16(offset, true) : view.getUint8(offset);
  offset += flags & 0x01 ? 2 : 1;
  // Contact is only meaningful when the sensor claims to support reporting it.
  const contact = flags & 0x04 ? Boolean(flags & 0x02) : null;
  if (flags & 0x08) offset += 2; // energy expended
  const rr: number[] = [];
  if (flags & 0x10)
    for (; offset + 2 <= view.byteLength; offset += 2)
      // Intervals are transmitted in units of 1/1024 s.
      rr.push(Math.round((view.getUint16(offset, true) * 1000) / 1024));
  return { hr, rr, contact };
}

export type BroadcastStatus = {
  broadcasting: boolean;
  /** Beats received since this connection opened -- proof the stream is live. */
  beats: number;
  /** Intervals seen, so the absence of HRV on a given sensor is visible. */
  intervals: number;
  rmssd: number | null;
  contact: boolean | null;
  toggle: () => Promise<void>;
  supported: boolean;
};

/** Stream measured heart rate from a Bluetooth sensor into the twin.
 *
 * Shared by the overview and the connections page so a demonstration can be
 * started from whichever screen is already open.
 */
export function useHeartRateBroadcast(
  notify: (message: string) => void,
  blocked?: () => boolean,
): BroadcastStatus {
  const device = useRef<{ gatt?: { disconnect: () => void } } | null>(null);
  const [broadcasting, setBroadcasting] = useState(false);
  const [beats, setBeats] = useState(0);
  const [intervals, setIntervals] = useState(0);
  const [rmssd, setRmssd] = useState<number | null>(null);
  const [contact, setContact] = useState<boolean | null>(null);

  // Web Bluetooth is feature-detected; Safari and iOS do not expose it.
  const supported =
    typeof navigator !== "undefined" &&
    Boolean((navigator as Navigator & { bluetooth?: unknown }).bluetooth);

  useEffect(() => () => device.current?.gatt?.disconnect(), []);

  async function toggle() {
    if (blocked?.()) return;
    if (broadcasting) {
      device.current?.gatt?.disconnect();
      setBroadcasting(false);
      return;
    }
    if (!supported) {
      notify(
        "Direct Bluetooth is unavailable in this browser. Use a desktop Chromium browser with your watch in heart-rate broadcast mode, or import a Garmin FIT activity.",
      );
      return;
    }
    const bluetooth = (
      navigator as Navigator & {
        bluetooth: { requestDevice: (options: unknown) => Promise<any> };
      }
    ).bluetooth;
    try {
      const found = await bluetooth.requestDevice({
        filters: [{ services: ["heart_rate"] }],
      });
      device.current = found;
      const server = await found.gatt.connect();
      const service = await server.getPrimaryService("heart_rate");
      const characteristic = await service.getCharacteristic(
        "heart_rate_measurement",
      );
      let inFlight = false;
      let pending: number[] = [];
      characteristic.addEventListener(
        "characteristicvaluechanged",
        async (e: any) => {
          const sample = readHeartRate(e.target.value as DataView);
          setBeats((n) => n + 1);
          setContact(sample.contact);
          if (sample.rr.length) setIntervals((n) => n + sample.rr.length);
          // Intervals accumulate across notifications rather than being dropped
          // while a request is in flight: a slow post costs latency, not beats.
          pending = pending.concat(sample.rr).slice(-32);
          if (inFlight) return;
          inFlight = true;
          const rr = pending;
          pending = [];
          try {
            const reply = await post<{ hrv_rmssd_ms: number | null }>(
              "/api/ingest/bluetooth",
              {
                heart_rate_bpm: sample.hr,
                rr_ms: rr,
                contact: sample.contact,
                event_time: new Date().toISOString(),
              },
            );
            if (reply?.hrv_rmssd_ms != null) setRmssd(reply.hrv_rmssd_ms);
          } catch (err) {
            pending = rr.concat(pending).slice(-32);
            notify((err as Error).message);
          } finally {
            inFlight = false;
          }
        },
      );
      await characteristic.startNotifications();
      setBroadcasting(true);
      setBeats(0);
      setIntervals(0);
      found.addEventListener("gattserverdisconnected", () => {
        setBroadcasting(false);
        notify(
          "Heart-rate broadcast disconnected. Your saved measurements remain available.",
        );
      });
      notify(
        "Live heart rate connected. Only measured heart rate and beat intervals are streamed; nothing else is inferred.",
      );
    } catch (e) {
      notify((e as Error).message);
    }
  }

  return {
    broadcasting,
    beats,
    intervals,
    rmssd,
    contact,
    toggle,
    supported,
  };
}
