import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";
const root = process.env.BIOTWIN_TEST_URL || "http://localhost:8000";
const browser = await chromium.launch({
  executablePath: process.env.BIOTWIN_TEST_BUNDLED_CHROMIUM
    ? undefined
    : process.env.CHROME_PATH ||
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
});
const report = {
  errors: [],
  instantTopics: [],
  autoplayRecovery: false,
  recording: false,
  voiceFailure: false,
  requestFailure: false,
  history: false,
  manualDismiss: false,
};
let registered = false;
await mkdir("test-results", { recursive: true });
try {
  const reg = await context.request.post(`${root}/auth/session/register`, {
    data: {
      email: `ui-voice-${Date.now()}@biotwin.invalid`,
      name: "Voice check",
      password: "voice-test-long-password",
      adult: true,
    },
  });
  assert.equal(reg.status(), 200);
  registered = true;
  const imported = await context.request.post(`${root}/api/ingest/file`, {
    multipart: {
      file: {
        name: "voice.json",
        mimeType: "application/json",
        buffer: Buffer.from(
          JSON.stringify([
            {
              event_time: new Date().toISOString(),
              heart_rate_bpm: 76,
              steps: 7100,
              active_kcal: 300,
            },
          ]),
        ),
      },
    },
  });
  assert.equal(imported.status(), 200);
  const samples = 48000,
    wav = Buffer.alloc(44 + samples * 2);
  wav.write("RIFF");
  wav.writeUInt32LE(wav.length - 8, 4);
  wav.write("WAVEfmt ", 8);
  wav.writeUInt32LE(16, 16);
  wav.writeUInt16LE(1, 20);
  wav.writeUInt16LE(1, 22);
  wav.writeUInt32LE(16000, 24);
  wav.writeUInt32LE(32000, 28);
  wav.writeUInt16LE(2, 32);
  wav.writeUInt16LE(16, 34);
  wav.write("data", 36);
  wav.writeUInt32LE(samples * 2, 40);
  for (let i = 0; i < samples; i++)
    wav.writeInt16LE(
      Math.round(Math.sin((i * 2 * Math.PI * 220) / 16000) * 1000),
      44 + i * 2,
    );
  const spoken = "Your recorded heart rate is 76.";
  const characters = [...spoken];
  const chunk = {
    audio_base64: wav.toString("base64"),
    alignment: {
      characters,
      character_start_times_seconds: characters.map(
        (_, i) => (i * 2.8) / characters.length,
      ),
      character_end_times_seconds: characters.map(
        (_, i) => ((i + 1) * 2.8) / characters.length,
      ),
    },
  };
  await context.addInitScript(() => {
    window.__plays = 0;
    window.__ended = 0;
    window.__blockPlay = false;
    window.__captions = 0;
    const Original = window.Audio;
    window.Audio = class extends Original {
      play() {
        if (window.__blockPlay) {
          window.__blockPlay = false;
          return Promise.reject(
            new DOMException("Gesture required", "NotAllowedError"),
          );
        }
        return super.play();
      }
      constructor(...args) {
        super(...args);
        this.addEventListener("playing", () => window.__plays++);
        this.addEventListener("ended", () => window.__ended++);
      }
    };
    if (window.MediaSource) window.MediaSource.isTypeSupported = () => false;
    navigator.mediaDevices.getUserMedia = async () => {
      const audio = new AudioContext();
      await audio.resume();
      const oscillator = audio.createOscillator();
      const destination = audio.createMediaStreamDestination();
      oscillator.connect(destination);
      oscillator.start();
      return destination.stream;
    };
  });
  await context.route("**/api/session", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), voice_configured: true },
    });
  });
  let answerGate = null;
  await context.route("**/api/twin/ask", async (route) => {
    const gate = answerGate;
    if (gate) {
      gate.entered();
      await gate.released;
    }
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), voice_configured: true },
    });
  });
  await context.route("**/api/voice/**", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/x-ndjson",
      body: JSON.stringify(chunk) + "\n",
    }),
  );
  const page = await context.newPage();
  page.on("pageerror", (e) => report.errors.push(e.message));
  await page.goto(root);
  await page.locator(".twin-hero canvas").waitFor();
  const ask = async (question, topic) => {
    let release, entered;
    const requestEntered = new Promise((resolve) => (entered = resolve));
    answerGate = {
      entered,
      released: new Promise((resolve) => (release = resolve)),
    };
    try {
      await page.getByLabel("Ask your twin", { exact: true }).fill(question);
      const request = page.waitForRequest("**/api/twin/ask");
      await page.getByLabel("Send question", { exact: true }).click();
      await request;
      await requestEntered;
      await page.locator(`[data-topic="${topic}"]`).waitFor();
      report.instantTopics.push(topic);
    } finally {
      release();
      answerGate = null;
    }
  };
  // Hold narration until the panel is visible: prove ordering without a CPU-speed assumption.
  for (const [question, topic] of [
    ["How is my heart rate?", "heart"],
    ["How did I sleep?", "sleep"],
    ["How many calories?", "calories"],
    ["How many steps?", "steps"],
    ["What is my plan?", "plan"],
  ]) {
    const ended = await page.evaluate(() => window.__ended);
    await ask(question, topic);
    await page.waitForFunction((n) => window.__ended > n, ended, {
      timeout: 20000,
    });
    await page.getByTestId("topic-takeover").waitFor({ state: "detached" });
  }
  await page.evaluate(() => (window.__blockPlay = true));
  await ask("What is my heart rate?", "heart");
  await page
    .getByRole("button", { name: "Tap to hear your twin", exact: false })
    .waitFor();
  assert.ok(await page.getByTestId("topic-takeover").isVisible());
  let ended = await page.evaluate(() => window.__ended);
  await page
    .getByRole("button", { name: "Tap to hear your twin", exact: false })
    .click();
  await page.waitForFunction((n) => window.__ended > n, ended);
  report.autoplayRecovery = true;
  await ask("What is my heart rate?", "heart");
  await page.getByLabel("Back to Overview", { exact: true }).click();
  await page.waitForTimeout(4000);
  assert.equal(await page.getByTestId("topic-takeover").count(), 0);
  report.manualDismiss = true;
  let recordingBytes = 0;
  await context.route("**/api/twin/transcribe", (route) => {
    recordingBytes = route.request().postDataBuffer()?.length ?? 0;
    return route.fulfill({ json: { question: "How many steps today?" } });
  });
  await page.getByLabel("Start listening", { exact: true }).click();
  await page.getByLabel("Stop listening", { exact: true }).waitFor();
  await page.waitForTimeout(400);
  ended = await page.evaluate(() => window.__ended);
  await page.getByLabel("Stop listening", { exact: true }).click();
  await page.locator('[data-topic="steps"]').waitFor();
  await page.waitForFunction((n) => window.__ended > n, ended);
  assert.ok(recordingBytes > 100);
  report.recording = true;
  await context.unroute("**/api/voice/**");
  await context.route("**/api/voice/**", (route) =>
    route.fulfill({ status: 502, json: { detail: "Speech is unavailable." } }),
  );
  await ask("How is my sleep?", "sleep");
  await page
    .getByRole("alert")
    .filter({ hasText: "voice is unavailable" })
    .waitFor();
  assert.ok(await page.getByTestId("topic-takeover").isVisible());
  report.voiceFailure = true;
  await context.unroute("**/api/twin/ask");
  await context.route("**/api/twin/ask", (route) =>
    route.fulfill({
      status: 503,
      json: { detail: "Please try again shortly." },
    }),
  );
  await page
    .getByLabel("Ask your twin", { exact: true })
    .fill("What are my steps?");
  await page.getByLabel("Send question", { exact: true }).click();
  await page
    .getByTestId("answer-panel")
    .getByText("Your twin is unavailable.", { exact: false })
    .waitFor();
  report.requestFailure = true;
  await page.reload();
  await page.getByLabel("Conversation history", { exact: true }).click();
  await page
    .getByRole("dialog", { name: "Conversation history" })
    .locator(".transcript-message")
    .first()
    .waitFor();
  report.history = true;
  await page.keyboard.press("Escape");
  assert.equal(
    await page.getByRole("dialog", { name: "Conversation history" }).count(),
    0,
  );
  assert.deepEqual(report.errors, []);
  console.log(JSON.stringify(report));
  await writeFile(
    "test-results/redesign-voice-regression-report.json",
    JSON.stringify(report, null, 2),
  );
} finally {
  if (registered) await context.request.delete(`${root}/api/data`);
  await browser.close();
}
