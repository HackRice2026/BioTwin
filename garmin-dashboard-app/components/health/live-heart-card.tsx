"use client";

import { useEffect, useRef, useState } from "react";
import { Heart } from "lucide-react";
import { IconBadge } from "./icon-badge";

const WS_URL =
  process.env.NEXT_PUBLIC_LIVE_HR_WS_URL ?? "ws://localhost:8765/ws";

/**
 * Same live pipeline as ble_hr_live.py's own page (localhost:8765) --
 * connects directly to that WebSocket rather than polling this app's own
 * API, since that push-based path is already verified working end to end.
 * This card is additive: if the BLE script isn't running, it just falls
 * back to "no live connection" and the rest of the dashboard (fed by the
 * InfluxDB-backed API routes) is unaffected.
 */
export function LiveHeartCard({ fallbackBpm }: { fallbackBpm: number | null }) {
  const [bpm, setBpm] = useState<number | null>(fallbackBpm);
  const [live, setLive] = useState(false);
  const [beat, setBeat] = useState(false);
  const beatTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let ws: WebSocket | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;

    const connect = () => {
      if (cancelled) return;
      ws = new WebSocket(WS_URL);
      ws.onopen = () => setLive(true);
      ws.onclose = () => {
        setLive(false);
        retryTimer = setTimeout(connect, 2000);
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (event) => {
        const msg = JSON.parse(event.data) as { hr: number };
        setBpm(msg.hr);
        setBeat(true);
        if (beatTimeout.current) clearTimeout(beatTimeout.current);
        beatTimeout.current = setTimeout(() => setBeat(false), 380);
      };
    };
    connect();

    return () => {
      cancelled = true;
      if (retryTimer) clearTimeout(retryTimer);
      ws?.close();
    };
  }, []);

  return (
    <div className="flex items-center gap-4 rounded-3xl bg-card border border-border p-5">
      <IconBadge
        icon={Heart}
        color="coral"
        size={56}
        className={beat ? "scale-110 transition-transform duration-150" : "transition-transform duration-150"}
      />
      <div>
        <div className="flex items-baseline gap-1.5">
          <span className="font-display text-5xl font-semibold text-foreground">
            {bpm ?? "--"}
          </span>
          <span className="text-sm text-muted-foreground">bpm</span>
        </div>
        <div className="mt-1 flex items-center gap-1.5">
          <span
            className={
              "h-1.5 w-1.5 rounded-full " + (live ? "bg-good" : "bg-critical")
            }
          />
          <span className="text-xs text-muted-foreground">
            {live ? "Live" : fallbackBpm != null ? "Last known" : "Not connected"}
          </span>
        </div>
      </div>
    </div>
  );
}
