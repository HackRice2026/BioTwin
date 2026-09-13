import assert from "node:assert/strict";
import { resolve } from "node:path";
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";
const root = process.env.BIOTWIN_TEST_URL || "http://localhost:5173";
const audio = process.env.BIOTWIN_QUESTION_WAV;
if (!audio)
  throw new Error(
    "Set BIOTWIN_QUESTION_WAV to a spoken WAV asking about steps. This check calls real providers.",
  );
const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH ||
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
  args: [
    "--use-fake-ui-for-media-stream",
    "--use-fake-device-for-media-stream",
    `--use-file-for-fake-audio-capture=${resolve(audio)}`,
  ],
});
const context = await browser.newContext({
  viewport: { width: 390, height: 844 },
  permissions: ["microphone"],
});
const report = {
  recordedAudio: true,
  physicalMicrophone: false,
  errors: [],
  captionChanges: [],
  events: [],
};
let registered = false;
try {
  const reg = await context.request.post(`${root}/auth/session/register`, {
    data: {
      email: `redesign-${Date.now()}@biotwin.invalid`,
      password: "biotwin-redesign-verification",
      name: "Voice check",
      adult: true,
    },
  });
  assert.equal(reg.status(), 200);
  registered = true;
  const now = Date.now();
  const frames = Array.from({ length: 7 }, (_, i) => ({
    event_time: new Date(now - (6 - i) * 86400000).toISOString(),
    heart_rate_bpm: 72 + i,
    resting_hr_bpm: 60,
    hrv_rmssd_ms: 45 + i,
    steps: 6200 + i * 150,
    active_kcal: 320 + i * 20,
    sleep: {
      start: new Date(now - (6 - i) * 86400000 - 9 * 3600000).toISOString(),
      end: new Date(now - (6 - i) * 86400000 - 3600000).toISOString(),
      total_minutes: 460,
      deep_minutes: 80,
      light_minutes: 270,
      rem_minutes: 110,
      awake_minutes: 20,
    },
  }));
  const upload = await context.request.post(`${root}/api/ingest/file`, {
    multipart: {
      file: {
        name: "verification.json",
        mimeType: "application/json",
        buffer: Buffer.from(JSON.stringify(frames)),
      },
    },
  });
  assert.equal(upload.status(), 200);
  await context.addInitScript(() => {
    window.__voiceEvents = [];
    window.__captions = [];
    window.__topicShownAt = null;
    const OriginalAudio = window.Audio;
    window.Audio = class extends OriginalAudio {
      constructor(...args) {
        super(...args);
        for (const type of ["playing", "ended", "pause", "error"])
          this.addEventListener(type, () =>
            window.__voiceEvents.push({
              type,
              time: performance.now(),
              audioTime: this.currentTime,
            }),
          );
      }
    };
    new MutationObserver(() => {
      if (
        document.querySelector('[data-testid="topic-takeover"]') &&
        !window.__topicShownAt
      )
        window.__topicShownAt = performance.now();
      const word = document
        .querySelector('[data-active="true"]')
        ?.textContent?.trim();
      if (word && window.__captions.at(-1)?.word !== word)
        window.__captions.push({ word, time: performance.now() });
    }).observe(document, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["data-active"],
    });
  });
  const page = await context.newPage();
  page.on("pageerror", (e) => report.errors.push(e.message));

  await page.goto(root);
  console.log("Page loaded");
  await page.locator(".twin-hero canvas").waitFor();
  await page.getByLabel("Start listening", { exact: true }).click();
  await page.getByLabel("Stop listening", { exact: true }).waitFor();
  console.log("Recording started");
  await page.waitForTimeout(Number(process.env.BIOTWIN_RECORD_MS || 4000));
  const transcribed = page.waitForResponse(
    (r) => r.url().endsWith("/api/twin/transcribe"),
    { timeout: 45000 },
  );
  const answered = page.waitForResponse(
    (r) => r.url().endsWith("/api/twin/ask") && r.request().method() === "POST",
    { timeout: 65000 },
  );
  const voiced = page.waitForResponse((r) => r.url().includes("/api/voice/"), {
    timeout: 80000,
  });
  transcribed.catch(() => {});
  answered.catch(() => {});
  voiced.catch(() => {});
  let questionRequestedAt;
  page.on("request", (r) => {
    if (r.url().endsWith("/api/twin/ask")) questionRequestedAt = Date.now();
  });
  await page.getByLabel("Stop listening", { exact: true }).click();
  console.log("Recording stopped");
  const tr = await transcribed;
  console.log("Transcription status", tr.status());
  if (tr.status() !== 200) console.log(await tr.text());
  assert.equal(tr.status(), 200);
  report.transcription = await tr.json();
  console.log("Transcription returned:", report.transcription.question);
  await page.locator('[data-topic="steps"]').waitFor({ timeout: 5000 });
  report.panelWithinMs = Date.now() - questionRequestedAt;
  assert.ok(
    report.panelWithinMs < 1000,
    "Topic must open before narration completes",
  );
  const answer = await answered;
  assert.equal(answer.status(), 200);
  const reply = await answer.json();
  report.narrationMode = reply.mode;
  report.narrationModel = reply.model;
  report.answer = reply.answer;
  assert.equal(reply.mode, "language_service");
  assert.match(reply.model, /^vertex:/);
  assert.match(reply.answer, /7,?100/);
  const speech = await voiced;
  assert.equal(speech.status(), 200);
  report.speechType = speech.headers()["content-type"];
  assert.match(report.speechType, /ndjson/);
  await page.waitForFunction(
    () => window.__voiceEvents.some((e) => e.type === "playing"),
    {},
    { timeout: 40000 },
  );
  await page.waitForFunction(
    () => window.__captions.length > 2,
    {},
    { timeout: 20000 },
  );
  await mkdir("test-results", { recursive: true });
  await page.screenshot({ path: "test-results/biotwin2-live-voice.png" });
  await page.waitForFunction(
    () => window.__voiceEvents.some((e) => e.type === "ended"),
    {},
    { timeout: 90000 },
  );
  await page
    .locator('[data-testid="topic-takeover"]')
    .waitFor({ state: "detached", timeout: 5000 });
  report.returnedToOverview = await page
    .getByRole("heading", { name: "Your essentials", exact: true })
    .isVisible();
  report.events = await page.evaluate(() => window.__voiceEvents);
  report.captionChanges = await page.evaluate(() => window.__captions);
  await page.reload();
  await page.getByLabel("Conversation history", { exact: true }).click();
  await page
    .getByRole("dialog", { name: "Conversation history" })
    .getByText(reply.answer, { exact: true })
    .waitFor();
  report.historyRestored = true;
  assert.equal(report.errors.length, 0);
  console.log(JSON.stringify(report, null, 2));
  await writeFile(
    "test-results/redesign-live-voice-report.json",
    JSON.stringify(report, null, 2),
  );
} catch (error) {
  console.error("Verification failed", error);
  const page = context.pages()[0];
  if (page) {
    await page.screenshot({ path: "test-results/biotwin2-voice-failure.png" });
    console.log(
      (await page.locator(".voice-feedback").allTextContents()).join(" | "),
    );
  }
  throw error;
} finally {
  if (registered) await context.request.delete(`${root}/api/data`);
  await browser.close();
}
