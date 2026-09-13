import { describe, expect, it } from "vitest";
import { fromBase64Pcm16, toBase64Pcm16 } from "./geminiLive";

describe("live audio encoding", () => {
  it("survives a round trip at 16-bit resolution", () => {
    const original = new Float32Array([0, 0.5, -0.5, 0.999, -0.999]);
    const back = fromBase64Pcm16(toBase64Pcm16(original));
    expect(back.length).toBe(original.length);
    original.forEach((value, i) => expect(back[i]).toBeCloseTo(value, 3));
  });

  it("clamps instead of wrapping, so a hot sample is not a loud click", () => {
    // Scaling 1.5 without clamping overflows int16 and flips sign -- audible as a
    // crack in the middle of speech.
    const back = fromBase64Pcm16(toBase64Pcm16(new Float32Array([1.5, -1.5])));
    expect(back[0]).toBeGreaterThan(0.99);
    expect(back[1]).toBeLessThan(-0.99);
  });

  it("encodes little-endian, which is what the API expects", () => {
    // 1.0 -> 0x7fff -> bytes ff 7f
    const bytes = atob(toBase64Pcm16(new Float32Array([1])));
    expect(bytes.charCodeAt(0)).toBe(0xff);
    expect(bytes.charCodeAt(1)).toBe(0x7f);
  });

  it("handles a chunk larger than one call-stack spread", () => {
    // The base64 step batches at 0x8000 bytes; a 2048-sample frame is fine but a
    // long reply is not, and String.fromCharCode(...) would blow the stack.
    const long = new Float32Array(70000).fill(0.25);
    const back = fromBase64Pcm16(toBase64Pcm16(long));
    expect(back.length).toBe(70000);
    expect(back[69999]).toBeCloseTo(0.25, 3);
  });
});
