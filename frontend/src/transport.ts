import { useEffect, useRef, useState } from "react";
import type { AvatarDrivers, TwinState } from "./contracts";
import type { OfflineBundle } from "./api";
import { api } from "./api";

export const idleDrivers: AvatarDrivers = {
  pulse_hz: null,
  breath_hz: null,
  fatigue: 0,
  exertion: 0,
  recovery_progress: 0,
};
export function useTwin(accountKey: number) {
  const live = useRef<TwinState | null>(null);
  const drivers = useRef<AvatarDrivers>(idleDrivers);
  const [state, setState] = useState<TwinState | null>(null);
  const [status, setStatus] = useState<"connecting" | "online" | "offline">(
    "connecting",
  );
  const [bundle, setBundle] = useState<OfflineBundle | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let stopped = false,
      socket: WebSocket | undefined,
      retry: ReturnType<typeof setTimeout> | undefined,
      fallback: ReturnType<typeof setInterval> | undefined,
      offline: OfflineBundle | null = null;
    let attempt = 0,
      lastSequence = 0,
      isOnline = false,
      lastMessage = Date.now();
    live.current = null;
    drivers.current = idleDrivers;
    setState(null);
    setStatus("connecting");
    const apply = (next: TwinState) => {
      live.current = next;
      drivers.current = next.drivers;
    };
    const showOffline = () => {
      if (stopped || isOnline || fallback || !offline) return;
      setStatus("offline");
      let index = 0;
      apply(offline.states[0]);
      setState(offline.states[0]);
      fallback = setInterval(() => {
        if (offline) apply(offline.states[++index % offline.states.length]);
      }, 1000);
    };
    api<OfflineBundle>("/offline.json")
      .then((data) => {
        offline = data;
        setBundle(data);
        if (!isOnline) showOffline();
      })
      .catch(() =>
        setError(
          "Offline assets are not available yet. Connect once to prepare offline mode.",
        ),
      );
    const connect = () => {
      if (stopped) return;
      socket = new WebSocket(
        `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/live`,
      );
      socket.onopen = () => {
        lastMessage = Date.now();
        socket?.send(
          JSON.stringify({ type: "hello", last_sequence: lastSequence }),
        );
      };
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data);
        lastMessage = Date.now();
        if (message.type === "state") {
          if (message.payload.schema_version !== "1.0.0") {
            setError(
              "The server uses an incompatible data contract. Update the app.",
            );
            socket?.close();
            return;
          }
          isOnline = true;
          attempt = 0;
          setStatus("online");
          setError("");
          if (fallback) {
            clearInterval(fallback);
            fallback = undefined;
          }
          const first = lastSequence === 0;
          lastSequence = message.payload.sequence;
          apply(message.payload);
          if (first) setState(message.payload);
          socket?.send(JSON.stringify({ type: "ack", sequence: lastSequence }));
        } else if (message.type === "heartbeat")
          socket?.send(JSON.stringify({ type: "heartbeat" }));
      };
      socket.onclose = () => {
        isOnline = false;
        showOffline();
        if (!stopped)
          retry = setTimeout(
            connect,
            Math.min(15000, 700 * 2 ** attempt++) + Math.random() * 500,
          );
      };
      socket.onerror = () => socket?.close();
    };
    connect();
    // Render-loop drivers live in refs; dashboard text/charts are deliberately sampled once per second.
    const ui = setInterval(() => {
      if (live.current) setState(live.current);
    }, 1000);
    const heartbeat = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) {
        if (Date.now() - lastMessage > 35000) socket.close();
        else socket.send(JSON.stringify({ type: "heartbeat" }));
      }
    }, 15000);
    const watchdog = setTimeout(showOffline, 2500);
    return () => {
      stopped = true;
      socket?.close();
      clearInterval(ui);
      clearInterval(heartbeat);
      clearTimeout(watchdog);
      if (retry) clearTimeout(retry);
      if (fallback) clearInterval(fallback);
    };
  }, [accountKey]);
  return { state, live, drivers, status, bundle, error };
}
