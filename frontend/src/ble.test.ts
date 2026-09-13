import { describe, expect, it } from "vitest";
import { readHeartRate } from "./ble";

/** Build a Heart Rate Measurement payload (characteristic 0x2A37). */
function packet(opts: {
  wide?: boolean;
  hr: number;
  contact?: boolean | "unsupported";
  energy?: number;
  rr?: number[];
}) {
  const flags =
    (opts.wide ? 0x01 : 0) |
    (opts.contact === "unsupported" ? 0 : 0x04) |
    (opts.contact === true ? 0x02 : 0) |
    (opts.energy !== undefined ? 0x08 : 0) |
    (opts.rr ? 0x10 : 0);
  const bytes: number[] = [flags];
  if (opts.wide) bytes.push(opts.hr & 0xff, opts.hr >> 8);
  else bytes.push(opts.hr);
  if (opts.energy !== undefined)
    bytes.push(opts.energy & 0xff, opts.energy >> 8);
  for (const ms of opts.rr ?? []) {
    const ticks = Math.round((ms * 1024) / 1000);
    bytes.push(ticks & 0xff, ticks >> 8);
  }
  return new DataView(new Uint8Array(bytes).buffer);
}

describe("readHeartRate", () => {
  it("reads an 8-bit rate", () => {
    expect(readHeartRate(packet({ hr: 72, contact: true }))).toMatchObject({
      hr: 72,
      contact: true,
      rr: [],
    });
  });

  it("reads a 16-bit rate above 255", () => {
    expect(readHeartRate(packet({ wide: true, hr: 300, contact: true })).hr).toBe(300);
  });

  it("reports off-body contact instead of hiding it", () => {
    expect(readHeartRate(packet({ hr: 61, contact: false })).contact).toBe(false);
  });

  it("returns null contact when the sensor does not support it", () => {
    expect(readHeartRate(packet({ hr: 61, contact: "unsupported" })).contact).toBeNull();
  });

  it("converts RR intervals from 1/1024 s to milliseconds", () => {
    // A dropped beat-interval field is the difference between having HRV and not.
    expect(readHeartRate(packet({ hr: 60, contact: true, rr: [1000, 980] })).rr).toEqual([
      1000, 980,
    ]);
  });

  it("steps over the energy field to find the intervals", () => {
    // Energy expended sits between the rate and the intervals; skipping it
    // misaligns every interval that follows.
    const out = readHeartRate(
      packet({ hr: 120, contact: true, energy: 512, rr: [500, 512] }),
    );
    expect(out).toMatchObject({ hr: 120, rr: [500, 512] });
  });

  it("handles a 16-bit rate with energy and intervals together", () => {
    const out = readHeartRate(
      packet({ wide: true, hr: 260, contact: true, energy: 40, rr: [430] }),
    );
    expect(out).toMatchObject({ hr: 260, rr: [430] });
  });
});
