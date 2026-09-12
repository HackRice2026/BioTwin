# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "bleak==0.22.3",
#   "influxdb==5.3.2",
#   "aiohttp==3.10.11",
# ]
# ///
"""
Live heart-rate streaming straight from the watch over Bluetooth LE,
bypassing Garmin Connect entirely (no polling, no cloud round-trip).

Requires "Broadcast Heart Rate" turned on on the watch
(Settings > Sensors > Heart Rate > Broadcast, or a toggle when starting
an activity) -- that's what makes it advertise the standard BLE Heart
Rate Service (0x180D) other devices can subscribe to.

Runs on the host, not in Docker -- Docker Desktop on Mac has no access
to host Bluetooth hardware.

Two independent output paths, both fed directly from the BLE notify
callback (neither is downstream of the other):
  - InfluxDB write -> feeds the "Live Workout" Grafana dashboard, which
    is a normal dashboard that polls a database on a timer. Fine for a
    persistent/historical view, not actually "live".
  - A tiny built-in WebSocket server (--ws-port, default 8765) that
    pushes every reading straight to any connected browser tab the
    instant it's parsed. No database, no query, no polling -- open
    http://localhost:8765 for the genuinely-live view.

Usage:
    uv run src/garmin_grafana/ble_hr_live.py --name Venu
    uv run src/garmin_grafana/ble_hr_live.py --address AA:BB:CC:DD:EE:FF
"""
import argparse
import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from aiohttp import web, WSMsgType
from bleak import BleakClient, BleakScanner
from influxdb import InfluxDBClient

HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("ble_hr_live")


@dataclass
class HRMeasurement:
    flags: int
    hr: int
    rr_intervals_seconds: list[float] = field(default_factory=list)

    @property
    def rr_present(self) -> bool:
        return bool(self.flags & 0x10)

    @property
    def energy_expended_present(self) -> bool:
        return bool(self.flags & 0x08)


def parse_hr_measurement(data: bytearray) -> HRMeasurement:
    """Full BLE Heart Rate Measurement parse (org.bluetooth.characteristic.heart_rate_measurement).

    The single HR byte/word Garmin exposes here is its own smoothed/averaged
    reading, updated on whatever cadence the watch's firmware chooses to
    re-broadcast it -- that's the cause of "skipping" spikes, not this
    script. If the device ALSO sets the RR-interval flag, it's including raw
    beat-to-beat timing (used for HRV), which gives real per-heartbeat
    resolution instead of the firmware's smoothed value. We use it when
    present.
    """
    flags = data[0]
    offset = 1

    if flags & 0x01:  # HR value is UINT16
        hr = int.from_bytes(data[offset:offset + 2], byteorder="little")
        offset += 2
    else:  # HR value is UINT8
        hr = data[offset]
        offset += 1

    if flags & 0x08:  # Energy Expended present (UINT16) -- skip it, we don't use it
        offset += 2

    rr_intervals_seconds = []
    if flags & 0x10:  # RR-Interval values present, one or more UINT16s to the end of the packet
        while offset + 1 < len(data):
            rr_raw = int.from_bytes(data[offset:offset + 2], byteorder="little")
            rr_intervals_seconds.append(rr_raw / 1024.0)  # spec units: 1/1024 second
            offset += 2

    return HRMeasurement(flags=flags, hr=hr, rr_intervals_seconds=rr_intervals_seconds)


async def find_device(name_substring: str | None, scan_timeout: float):
    log.info(f"Scanning for {scan_timeout}s for BLE heart rate devices...")
    devices = await BleakScanner.discover(timeout=scan_timeout, return_adv=True)
    candidates = []
    for device, adv in devices.values():
        has_hr_service = HR_SERVICE_UUID in [u.lower() for u in (adv.service_uuids or [])]
        name = device.name or ""
        name_matches = name_substring.lower() in name.lower() if name_substring else True
        if has_hr_service and name_matches:
            candidates.append(device)

    if not candidates:
        log.error(
            "No matching BLE heart rate devices found. Make sure 'Broadcast Heart "
            "Rate' is turned on on the watch, and that it's awake/nearby (broadcast "
            "mode usually only advertises while an activity is active)."
        )
        return None

    if len(candidates) > 1:
        log.warning("Multiple candidates found, using the first one:")
        for d in candidates:
            log.warning(f"  {d.name} ({d.address})")

    chosen = candidates[0]
    log.info(f"Using device: {chosen.name} ({chosen.address})")
    return chosen


LIVE_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>Live Heart Rate</title>
<style>
  .viz-root {
    color-scheme: dark;
    --page:      #0d0d0d;
    --surface:   #1a1a19;
    --ink:       #ffffff;
    --ink-2:     #c3c2b7;
    --muted:     #898781;
    --grid:      #2c2c2a;
    --series:    #e66767;
    --series-fill: rgba(230, 103, 103, 0.10);
    --good:      #0ca30c;
    --critical:  #d03b3b;
  }
  @media (prefers-color-scheme: light) {
    .viz-root:not([data-forced-dark]) {
      color-scheme: light;
      --page:      #f9f9f7;
      --surface:   #fcfcfb;
      --ink:       #0b0b0b;
      --ink-2:     #52514e;
      --muted:     #898781;
      --grid:      #e1e0d9;
      --series:    #e34948;
      --series-fill: rgba(227, 73, 72, 0.10);
    }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    background: var(--page); color: var(--ink);
    font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
    margin: 0; padding: 24px 20px 12px;
    display: flex; flex-direction: column; align-items: center; gap: 14px;
  }
  .status-row { display: flex; align-items: center; gap: 8px; align-self: flex-start; }
  .dot { width: 9px; height: 9px; border-radius: 50%; background: var(--critical); transition: background 120ms; flex: none; }
  .dot.live { background: var(--good); }
  .status-text { font-size: 13px; color: var(--ink-2); letter-spacing: 0.02em; }
  .device { font-size: 13px; color: var(--muted); }

  .hero-row { display: flex; align-items: center; gap: 18px; }
  .heart {
    width: 46px; height: 46px; flex: none; color: var(--series);
    transform-origin: center; transform: scale(1);
  }
  .heart.beat { animation: pulse 380ms cubic-bezier(.2,.8,.3,1); }
  @keyframes pulse {
    0%   { transform: scale(1); }
    30%  { transform: scale(1.32); }
    100% { transform: scale(1); }
  }
  #bpm {
    font-size: clamp(96px, 20vw, 190px); font-weight: 700; line-height: 1;
    font-variant-numeric: proportional-nums;
    color: var(--ink);
  }
  #unit { font-size: 15px; color: var(--muted); letter-spacing: 0.14em; text-transform: uppercase; margin-top: -6px; }

  .stats-row { display: flex; gap: 28px; }
  .stat { text-align: center; }
  .stat-label { font-size: 11px; color: var(--muted); letter-spacing: 0.1em; text-transform: uppercase; }
  .stat-value { font-size: 20px; color: var(--ink-2); font-weight: 600; margin-top: 2px; }

  .chart-wrap { position: relative; width: 100%; max-width: 920px; }
  canvas { width: 100%; display: block; background: var(--surface); border-radius: 10px; }
  .tooltip {
    position: absolute; pointer-events: none; opacity: 0; transition: opacity 100ms;
    background: var(--surface); border: 1px solid var(--grid); border-radius: 6px;
    padding: 6px 10px; font-size: 12px; color: var(--ink-2); white-space: nowrap;
    transform: translate(-50%, -120%);
  }
  .tooltip .v { color: var(--ink); font-weight: 700; font-size: 14px; }
</style></head>
<body class="viz-root">
  <div class="status-row">
    <span class="dot" id="dot"></span>
    <span class="status-text" id="statusText">Connecting&hellip;</span>
    <span class="device" id="deviceText"></span>
  </div>

  <div class="hero-row">
    <svg class="heart" id="heart" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
      <path d="M12 21s-6.7-4.35-9.3-8.2C.86 10.1 1.4 6.6 4.2 5.1c2.2-1.2 4.6-.4 5.9 1.4.4.5.7 1 1 1.5.3-.5.6-1 1-1.5 1.3-1.8 3.7-2.6 5.9-1.4 2.8 1.5 3.34 5 1.5 7.7C18.7 16.65 12 21 12 21z"/>
    </svg>
    <div>
      <div id="bpm">&ndash;&ndash;</div>
      <div id="unit">bpm &middot; pushed live, no polling</div>
    </div>
  </div>

  <div class="stats-row">
    <div class="stat"><div class="stat-label">Min</div><div class="stat-value" id="statMin">&ndash;</div></div>
    <div class="stat"><div class="stat-label">Avg</div><div class="stat-value" id="statAvg">&ndash;</div></div>
    <div class="stat"><div class="stat-label">Max</div><div class="stat-value" id="statMax">&ndash;</div></div>
  </div>

  <div class="chart-wrap">
    <canvas id="chart" height="200"></canvas>
    <div class="tooltip" id="tooltip"><span class="v" id="tooltipV"></span> bpm &middot; <span id="tooltipT"></span></div>
  </div>

<script>
  const dot = document.getElementById('dot');
  const statusText = document.getElementById('statusText');
  const deviceText = document.getElementById('deviceText');
  const heart = document.getElementById('heart');
  const bpmEl = document.getElementById('bpm');
  const statMin = document.getElementById('statMin');
  const statAvg = document.getElementById('statAvg');
  const statMax = document.getElementById('statMax');
  const canvas = document.getElementById('chart');
  const ctx = canvas.getContext('2d');
  const tooltip = document.getElementById('tooltip');
  const tooltipV = document.getElementById('tooltipV');
  const tooltipT = document.getElementById('tooltipT');

  const MAX_POINTS = 120;
  const points = []; // {hr, t}
  const styles = getComputedStyle(document.body);
  const cssVar = (name) => styles.getPropertyValue(name).trim();

  function resize() {
    const rect = canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = rect.width * dpr;
    canvas.height = rect.height * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    draw();
  }
  window.addEventListener('resize', resize);

  function niceRange(min, max) {
    const pad = Math.max(4, (max - min) * 0.15);
    return [Math.floor(min - pad), Math.ceil(max + pad)];
  }

  function draw() {
    const w = canvas.getBoundingClientRect().width;
    const h = canvas.getBoundingClientRect().height;
    ctx.clearRect(0, 0, w, h);
    if (points.length < 2) return;

    const values = points.map(p => p.hr);
    const [lo, hi] = niceRange(Math.min(...values), Math.max(...values));
    const xAt = (i) => (i / (MAX_POINTS - 1)) * w;
    const yAt = (v) => h - ((v - lo) / (hi - lo)) * h;

    const grid = cssVar('--grid');
    ctx.strokeStyle = grid;
    ctx.lineWidth = 1;
    for (let g = 0; g <= 3; g++) {
      const y = Math.round((h / 3) * g) + 0.5;
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(w, y); ctx.stroke();
    }

    const series = cssVar('--series');
    const seriesFill = cssVar('--series-fill');
    const offset = MAX_POINTS - points.length;

    ctx.beginPath();
    points.forEach((p, i) => {
      const x = xAt(i + offset), y = yAt(p.hr);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.lineTo(xAt(points.length - 1 + offset), h);
    ctx.lineTo(xAt(offset), h);
    ctx.closePath();
    ctx.fillStyle = seriesFill;
    ctx.fill();

    ctx.beginPath();
    points.forEach((p, i) => {
      const x = xAt(i + offset), y = yAt(p.hr);
      i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
    });
    ctx.strokeStyle = series;
    ctx.lineWidth = 2;
    ctx.lineJoin = 'round';
    ctx.lineCap = 'round';
    ctx.stroke();

    const last = points[points.length - 1];
    const lx = xAt(points.length - 1 + offset), ly = yAt(last.hr);
    ctx.beginPath();
    ctx.arc(lx, ly, 5, 0, Math.PI * 2);
    ctx.fillStyle = series;
    ctx.fill();
    ctx.lineWidth = 2;
    ctx.strokeStyle = cssVar('--surface');
    ctx.stroke();

    canvas._plot = { xAt, yAt, offset, lo, hi, w, h };
  }

  canvas.addEventListener('mousemove', (e) => {
    if (!canvas._plot || points.length < 2) return;
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const { xAt, offset } = canvas._plot;
    let nearest = 0, best = Infinity;
    points.forEach((p, i) => {
      const d = Math.abs(xAt(i + offset) - mx);
      if (d < best) { best = d; nearest = i; }
    });
    const p = points[nearest];
    const x = xAt(nearest + offset), y = canvas._plot.yAt(p.hr);
    tooltip.style.opacity = 1;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
    tooltipV.textContent = p.hr;
    const secsAgo = Math.round((Date.now() - p.t) / 1000);
    tooltipT.textContent = secsAgo <= 1 ? 'just now' : secsAgo + 's ago';
  });
  canvas.addEventListener('mouseleave', () => { tooltip.style.opacity = 0; });

  function beatPulse() {
    heart.classList.remove('beat');
    void heart.offsetWidth; // restart the animation
    heart.classList.add('beat');
  }

  function updateStats() {
    const values = points.map(p => p.hr);
    statMin.textContent = Math.min(...values);
    statMax.textContent = Math.max(...values);
    statAvg.textContent = Math.round(values.reduce((a, b) => a + b, 0) / values.length);
  }

  function connect() {
    const ws = new WebSocket((location.protocol === 'https:' ? 'wss://' : 'ws://') + location.host + '/ws');
    ws.onopen = () => { dot.classList.add('live'); statusText.textContent = 'Live'; };
    ws.onclose = () => { dot.classList.remove('live'); statusText.textContent = 'Reconnecting…'; setTimeout(connect, 1000); };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      bpmEl.textContent = msg.hr;
      if (msg.device) deviceText.textContent = '· ' + msg.device;
      beatPulse();
      points.push({ hr: msg.hr, t: Date.now() });
      if (points.length > MAX_POINTS) points.shift();
      updateStats();
      draw();
    };
  }
  resize();
  connect();
</script>
</body></html>"""


class LiveHub:
    """Fan-out to every connected browser tab. No storage, no query -- a
    reading is broadcast the instant it's handed in, then forgotten."""

    def __init__(self):
        self.clients: set[web.WebSocketResponse] = set()

    async def broadcast(self, payload: dict):
        if not self.clients:
            return
        message = json.dumps(payload)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send_str(message)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)


async def start_ws_server(hub: LiveHub, port: int):
    async def index(_request):
        return web.Response(text=LIVE_HTML, content_type="text/html")

    async def ws_handler(request):
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        hub.clients.add(ws)
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    break
        finally:
            hub.clients.discard(ws)
        return ws

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/ws", ws_handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()
    log.info(f"Live view (no polling, pure push): http://localhost:{port}")


def write_point(influx_client: InfluxDBClient, device_name: str, hr: int, received_at: datetime):
    point = {
        "measurement": "HeartRateLive",
        "time": received_at.isoformat(),
        "tags": {"Device": device_name},
        "fields": {"HeartRate": hr},
    }
    try:
        influx_client.write_points([point], time_precision="u")
    except Exception as err:
        log.error(f"InfluxDB write failed (dropped this reading): {err}")


async def stream(address: str, device_name: str, influx_client: InfluxDBClient, hub: LiveHub):
    disconnected = asyncio.Event()
    loop = asyncio.get_running_loop()
    flags_logged = False

    def on_disconnect(_client):
        log.warning("Device disconnected.")
        disconnected.set()

    def emit(instant_bpm: int, t: datetime):
        # Two independent fan-outs from the same event, neither waiting on
        # the other: InfluxDB write goes to a worker thread (a slow HTTP
        # call must never stall the next BLE notify), and the WebSocket
        # broadcast is scheduled on the loop directly since it's already
        # async and non-blocking -- that one reaches the browser with
        # nothing in between but a local socket write.
        loop.run_in_executor(None, write_point, influx_client, device_name, instant_bpm, t)
        loop.create_task(hub.broadcast({"hr": instant_bpm, "ts": t.isoformat(), "device": device_name}))

    def on_notify(_char, data: bytearray):
        # Timestamp and parse immediately on receipt -- this is as close to
        # the actual BLE packet arrival as we get.
        nonlocal flags_logged
        received_at = datetime.now(timezone.utc)
        m = parse_hr_measurement(data)

        if not flags_logged:
            flags_logged = True
            log.info(
                f"First packet: flags=0x{m.flags:02x}  rr_interval_present={m.rr_present}  "
                f"energy_expended_present={m.energy_expended_present}"
                + ("" if m.rr_present else "  -- no RR data from this device; stuck with its smoothed HR field, can't get finer resolution than that in software")
            )

        if m.rr_intervals_seconds:
            # RR values are oldest-to-newest and end at "now" (when this
            # packet was received) -- walk forward from (now - total RR
            # duration) so each derived beat gets its own real timestamp
            # instead of every beat in the packet colliding on `received_at`.
            t = received_at - timedelta(seconds=sum(m.rr_intervals_seconds))
            for rr in m.rr_intervals_seconds:
                t += timedelta(seconds=rr)
                instant_bpm = round(60.0 / rr) if rr > 0 else m.hr
                log.info(f"beat: {instant_bpm} bpm  (RR={rr * 1000:.0f}ms)")
                emit(instant_bpm, t)
        else:
            log.info(f"HR={m.hr} bpm")
            emit(m.hr, received_at)

    async with BleakClient(address, disconnected_callback=on_disconnect) as client:
        await client.start_notify(HR_MEASUREMENT_UUID, on_notify)
        log.info("Subscribed. Streaming live heart rate — Ctrl+C to stop.")
        await disconnected.wait()


async def main_async(args):
    influx_client = InfluxDBClient(
        host=args.influx_host,
        port=args.influx_port,
        username=args.influx_user,
        password=args.influx_password,
        database=args.influx_database,
    )

    hub = LiveHub()
    if not args.no_ws:
        await start_ws_server(hub, args.ws_port)

    while True:
        address = args.address
        device_name = args.name or "Garmin"
        if not address:
            device = await find_device(args.name, args.scan_timeout)
            if device is None:
                await asyncio.sleep(5)
                continue
            address = device.address
            device_name = device.name or device_name

        try:
            await stream(address, device_name, influx_client, hub)
        except Exception as err:
            log.error(f"Connection lost or failed: {err}")

        log.info("Reconnecting in 3 seconds...")
        await asyncio.sleep(3)


async def list_all_async(scan_timeout: float):
    log.info(f"Scanning for {scan_timeout}s — listing EVERY BLE device seen, no filtering...")
    devices = await BleakScanner.discover(timeout=scan_timeout, return_adv=True)
    if not devices:
        log.error("No BLE devices seen at all. Bluetooth radio issue on the Mac, most likely.")
        return
    for device, adv in devices.values():
        uuids = adv.service_uuids or []
        has_hr = HR_SERVICE_UUID in [u.lower() for u in uuids]
        marker = "  <-- has HR service!" if has_hr else ""
        print(f"{device.address}  rssi={adv.rssi:>5}  name={device.name!r:20}  uuids={uuids}{marker}")


def main():
    parser = argparse.ArgumentParser(description="Stream live heart rate from a Garmin watch over BLE into InfluxDB")
    parser.add_argument("--name", default=None, help="Substring to match the watch's advertised BLE name (e.g. 'Venu')")
    parser.add_argument("--address", default=None, help="Connect directly to this BLE address, skipping the scan")
    parser.add_argument("--scan-timeout", type=float, default=10.0)
    parser.add_argument("--list-all", action="store_true", help="Diagnostic: list every nearby BLE device and what it advertises, then exit")
    parser.add_argument("--ws-port", type=int, default=8765, help="Port for the live push-based browser view (http://localhost:PORT)")
    parser.add_argument("--no-ws", action="store_true", help="Disable the built-in live WebSocket/HTTP server")
    parser.add_argument("--influx-host", default="localhost")
    parser.add_argument("--influx-port", type=int, default=8086)
    parser.add_argument("--influx-user", default="influxdb_user")
    parser.add_argument("--influx-password", default="influxdb_secret_password")
    parser.add_argument("--influx-database", default="GarminStats")
    args = parser.parse_args()

    try:
        if args.list_all:
            asyncio.run(list_all_async(args.scan_timeout))
        else:
            asyncio.run(main_async(args))
    except KeyboardInterrupt:
        log.info("Stopped.")


if __name__ == "__main__":
    main()
