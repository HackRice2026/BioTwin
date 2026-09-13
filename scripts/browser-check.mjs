import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";
import { mkdir, writeFile } from "node:fs/promises";
const browser = await chromium.launch({
  executablePath: process.env.BIOTWIN_TEST_BUNDLED_CHROMIUM
    ? undefined
    : process.env.CHROME_PATH ||
      "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
const context = await browser.newContext({
  viewport: { width: 1440, height: 1100 },
  deviceScaleFactor: 1,
});
const page = await context.newPage();
await mkdir("test-results", { recursive: true });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(process.env.BIOTWIN_TEST_URL || "http://localhost:8000");
await page.getByText("Your day, understood.", { exact: true }).waitFor();
await page.locator("canvas").waitFor();
await page.getByText("Synthetic demo", { exact: true }).waitFor();
await page.screenshot({ path: "test-results/desktop.png", fullPage: true });

console.log(
  JSON.stringify({
    errors,
    canvas: await page.locator("canvas").count(),
    horizontalOverflow: await page.evaluate(
      () => document.documentElement.scrollWidth > innerWidth,
    ),
  }),
);
await page.getByRole("button", { name: "What-if lab", exact: false }).click();
await page.getByRole("button", { name: "Get moving", exact: false }).click();
await page
  .getByRole("heading", { name: "SIMULATED heart-rate trajectory" })
  .waitFor();
await page.screenshot({ path: "test-results/simulation.png", fullPage: true });
await page
  .getByRole("button", { name: "Talk to my twin", exact: true })
  .click();
await page
  .getByRole("textbox", { name: "Ask your twin" })
  .fill("Why am I tired today?");
await page.getByRole("button", { name: "Send question", exact: true }).click();
// dev's voice refactor speaks the answer on arrival instead of offering a
// "Listen with ElevenLabs" button, so wait for the answer itself.
await page.locator(".chat-answer, .chat-log .answer, .chat-twin").first().waitFor();
await page.screenshot({ path: "test-results/chat.png" });
await page.getByRole("button", { name: "Close conversation" }).click();
await page.getByRole("button", { name: "Overview", exact: true }).click();
await page.setViewportSize({ width: 390, height: 844 });
await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
const mobileOverflow = await page.evaluate(
  () => document.documentElement.scrollWidth > innerWidth,
);
await page.evaluate(() => navigator.serviceWorker.ready);
await page.waitForFunction(() => !!navigator.serviceWorker.controller);
const cached = await page.evaluate(() => caches.keys());
if (!cached.length) throw new Error("Offline precache was not created");
await context.setOffline(true);
await page.reload();
await page
  .getByText("OFFLINE / REPLAY", { exact: true })
  .waitFor({ timeout: 20000 });
await page.locator("canvas").waitFor();
await page.screenshot({ path: "test-results/offline.png", fullPage: true });
await page.getByRole("button", { name: "What-if lab", exact: false }).click();
await page
  .getByRole("button", { name: "Take a breather", exact: false })
  .click();
await page
  .getByRole("heading", { name: "SIMULATED heart-rate trajectory" })
  .waitFor();
await mkdir("test-results", { recursive: true });
await writeFile(
  "test-results/browser-report.json",
  JSON.stringify({ errors, mobileOverflow, offlinePassed: true }, null, 2),
);
console.log(JSON.stringify({ errors, mobileOverflow, offlinePassed: true }));
await browser.close();
