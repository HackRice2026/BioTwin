# /// script
# requires-python = ">=3.10"
# dependencies = [
#   "bleak==0.22.3",
#   "influxdb==5.3.2",
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

Usage:
    uv run src/garmin_grafana/ble_hr_live.py --name Venu
    uv run src/garmin_grafana/ble_hr_live.py --address AA:BB:CC:DD:EE:FF
"""
import argparse
import asyncio
import logging
from datetime import datetime, timezone

from bleak import BleakClient, BleakScanner
from influxdb import InfluxDBClient

HR_SERVICE_UUID = "0000180d-0000-1000-8000-00805f9b34fb"
HR_MEASUREMENT_UUID = "00002a37-0000-1000-8000-00805f9b34fb"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
log = logging.getLogger("ble_hr_live")


def parse_hr_measurement(data: bytearray) -> int:
    flags = data[0]
    uint16_format = flags & 0x01
    if uint16_format:
        return int.from_bytes(data[1:3], byteorder="little")
    return data[1]


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


async def stream(address: str, device_name: str, influx_client: InfluxDBClient):
    disconnected = asyncio.Event()
    loop = asyncio.get_running_loop()

    def on_disconnect(_client):
        log.warning("Device disconnected.")
        disconnected.set()

    def on_notify(_char, data: bytearray):
        # Timestamp and parse immediately on receipt (this is as close to the
        # BLE packet arrival as we get), then hand the network write off to a
        # worker thread so it can never stall processing of the next notify —
        # a blocking HTTP call here would otherwise queue up behind every
        # subsequent heartbeat and add latency that compounds over time.
        received_at = datetime.now(timezone.utc)
        hr = parse_hr_measurement(data)
        log.info(f"HR={hr} bpm")
        loop.run_in_executor(None, write_point, influx_client, device_name, hr, received_at)

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
            await stream(address, device_name, influx_client)
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
