import assert from "node:assert/strict";
import { mkdir, writeFile } from "node:fs/promises";
import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";
const live = process.env.BIOTWIN_LIVE_VOICE === "true";
const root = process.env.BIOTWIN_TEST_URL || "http://localhost:8000";
const browser = await chromium.launch({
  executablePath: process.env.BIOTWIN_TEST_BUNDLED_CHROMIUM
    ? undefined
    : process.env.CHROME_PATH ||
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1050 },
});
const report = {
  liveProviders: live,
  playingEvents: 0,
  historyRestored: false,
  spokenInput: false,
  voiceFailureVisible: false,
  requestFailureVisible: false,
  errors: [],
  autoplayRetried: false,
  recordingFallback: false,
};
let page;
try {
  await context.addInitScript(
    ({ live }) => {
      window.__voiceEvents = [];
      window.__blockNextPlay =
        !live && !sessionStorage.getItem("voice-unblocked");
      const NativeAudio = window.Audio;
      window.Audio = class extends NativeAudio {
        play() {
          if (window.__blockNextPlay) {
            window.__blockNextPlay = false;
            sessionStorage.setItem("voice-unblocked", "true");
            return Promise.reject(
              new DOMException("Gesture required", "NotAllowedError"),
            );
          }
          return super.play();
        }
        constructor(...args) {
          super(...args);
          for (const name of ["playing", "ended", "pause", "error"])
            this.addEventListener(name, () => window.__voiceEvents.push(name));
        }
      };
      window.SpeechRecognition = class {
        start() {
          this.onstart?.();
          setTimeout(() => {
            this.onresult?.({
              results: [[{ transcript: "What is my sleep duration?" }]],
            });
            this.onend?.();
          }, 30);
        }
        abort() {
          this.onend?.();
        }
        stop() {
          this.onend?.();
        }
      };
      if (!live && window.MediaSource)
        window.MediaSource.isTypeSupported = () => false;
    },
    { live },
  );
  const registration = await context.request.post(
    `${root}/auth/session/register`,
    {
      data: {
        email: `voice-${Date.now()}@biotwin.invalid`,
        password: "voice-browser-test-password",
        adult: true,
      },
    },
  );
  assert.equal(registration.status(), 200);
  const upload = await context.request.post(`${root}/api/ingest/file`, {
    multipart: {
      file: {
        name: "voice-measurement.json",
        mimeType: "application/json",
        buffer: Buffer.from(
          JSON.stringify([
            { event_time: new Date().toISOString(), heart_rate_bpm: 76 },
          ]),
        ),
      },
    },
  });
  assert.equal(upload.status(), 200);
  if (!live) {
    // A generated tone exercises real browser decoding/playback without calling paid providers in CI.
    const count = 16000,
      wav = Buffer.alloc(44 + count * 2);
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
    wav.writeUInt32LE(count * 2, 40);
    for (let i = 0; i < count; i++)
      wav.writeInt16LE(
        Math.round(Math.sin((i * 2 * Math.PI * 220) / 16000) * 1000),
        44 + i * 2,
      );
    await context.route("**/api/twin/ask", async (route) => {
      const response = await route.fetch();
      const body = await response.json();
      await route.fulfill({
        response,
        json: { ...body, voice_configured: true },
      });
    });
    await context.route("**/api/session", async (route) => {
      const response = await route.fetch();
      await route.fulfill({
        response,
        json: { ...(await response.json()), voice_configured: true },
      });
    });
    await context.route("**/api/voice/*", (route) =>
      route.fulfill({ status: 200, contentType: "audio/wav", body: wav }),
    );
  }
  page = await context.newPage();
  page.on("pageerror", (error) => report.errors.push(error.message));
  await page.goto(root);
  await page
    .getByRole("button", { name: "Talk to my twin", exact: true })
    .click();
  const typed =
    "What is my latest recorded heart rate? Reply with a single short sentence.";
  await page.getByLabel("Ask your twin", { exact: true }).fill(typed);
  const replyPromise = page.waitForResponse(
    (response) =>
      response.url().endsWith("/api/twin/ask") &&
      response.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Send question", exact: true })
    .click();
  const reply = await (await replyPromise).json();
  assert.equal(reply.mode, live ? "language_service" : "template");
  assert.match(reply.answer, /76/);
  if (!live) {
    await page
      .getByText(
        "Audio is ready. Tap Listen with ElevenLabs to allow playback.",
        { exact: true },
      )
      .waitFor();
    await page
      .getByRole("button", { name: "Listen with ElevenLabs", exact: true })
      .click();
    report.autoplayRetried = true;
  }
  await page.waitForFunction(
    () => window.__voiceEvents.includes("playing"),
    {},
    { timeout: 30000 },
  );
  await page
    .getByRole("button", { name: "Stop speaking", exact: true })
    .waitFor();
  await mkdir("test-results", { recursive: true });
  await page.screenshot({
    path: "test-results/voice-speaking.png",
    fullPage: true,
  });
  await page.waitForFunction(
    () => window.__voiceEvents.includes("ended"),
    {},
    { timeout: 30000 },
  );
  report.playingEvents += await page.evaluate(
    () => window.__voiceEvents.filter((x) => x === "playing").length,
  );
  await page.reload();
  await page
    .getByRole("button", { name: "Talk to my twin", exact: true })
    .click();
  await page.getByText(reply.answer, { exact: true }).first().waitFor();
  report.historyRestored = true;
  await page
    .getByRole("button", { name: "Dictate a question", exact: true })
    .click();
  await page.getByText("What is my sleep duration?", { exact: true }).waitFor();
  await page.waitForFunction(
    () => window.__voiceEvents.includes("playing"),
    {},
    { timeout: 30000 },
  );
  await page
    .getByRole("button", { name: "Stop speaking", exact: true })
    .click();
  const history = await (
    await context.request.get(`${root}/api/twin/conversations`)
  ).json();
  assert.equal(history.conversations.length, 2);
  assert.equal(history.conversations[1].question, "What is my sleep duration?");
  report.spokenInput = true;
  if (!live) {
    await page.evaluate(async () => {
      window.SpeechRecognition = undefined;
      window.webkitSpeechRecognition = undefined;
      window.__voiceEvents = [];
      const sound = new AudioContext();
      const source = sound.createOscillator();
      const destination = sound.createMediaStreamDestination();
      source.connect(destination);
      source.start();
      await sound.resume();
      window.__micSound = sound;
      window.__micStream = destination.stream;
      navigator.mediaDevices.getUserMedia = async () => destination.stream;
    });
    let recordedUpload = false;
    await context.route("**/api/twin/transcribe", async (route) => {
      assert(route.request().postDataBuffer().length > 100);
      recordedUpload = true;
      await route.fulfill({json:{question:"What is my latest recorded heart rate?"}});
    });
    await page.getByRole("button", {name:"Dictate a question",exact:true}).click();
    await page.getByRole("button", {name:"Finish dictation",exact:true}).waitFor();
    await page.waitForTimeout(150);
    await page.getByRole("button", {name:"Finish dictation",exact:true}).click();
    await page.waitForFunction(() => window.__voiceEvents.includes("playing"), {}, {timeout:10000});
    assert(recordedUpload);
    assert(await page.evaluate(() => window.__micStream.getTracks().every(track => track.readyState === "ended")));
    await page.evaluate(() => window.__micSound.close());
    await page.getByRole("button", {name:"Stop speaking",exact:true}).click();
    report.recordingFallback = true;
  }
  await context.route("**/api/voice/*", (route) =>
    route.fulfill({
      status: 502,
      contentType: "application/json",
      body: JSON.stringify({
        detail: "ElevenLabs is unavailable. Your text answer is saved.",
      }),
    }),
  );
  await page
    .getByRole("button", { name: "Listen with ElevenLabs", exact: true })
    .first()
    .click();
  await page
    .getByRole("alert")
    .filter({ hasText: "ElevenLabs is unavailable" })
    .waitFor();
  await page.getByText(reply.answer, { exact: true }).first().waitFor();
  report.voiceFailureVisible = true;
  await context.route("**/api/twin/ask", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/json",
      body: JSON.stringify({ detail: "Service unavailable" }),
    }),
  );
  await page
    .getByLabel("Ask your twin", { exact: true })
    .fill("Try another question");
  await page
    .getByRole("button", { name: "Send question", exact: true })
    .click();
  await page
    .getByText("Your twin is unavailable. Service unavailable", { exact: true })
    .waitFor();
  report.requestFailureVisible = true;
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({
    path: "test-results/voice-mobile.png",
    fullPage: true,
  });
  assert.equal(
    await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
    false,
  );
  assert.deepEqual(report.errors, []);
  console.log(JSON.stringify(report));
  await writeFile(
    "test-results/voice-report.json",
    JSON.stringify(report, null, 2),
  );
} catch (error) {
  if (page) {
    await mkdir("test-results", { recursive: true });
    await page.screenshot({
      path: "test-results/voice-failure.png",
      fullPage: true,
    });
    console.log(
      "Voice status:",
      await page.locator(".conversation-status").allTextContents(),
    );
    console.log(
      "Media events:",
      await page.evaluate(() => window.__voiceEvents),
    );
  }
  throw error;
} finally {
  await context.request.delete(`${root}/api/data`).catch(() => {});
  await browser.close();
}
