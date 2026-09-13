import { chromium } from "../frontend/node_modules/playwright-core/index.mjs";
import { writeFile } from "node:fs/promises";
const browser = await chromium.launch({
  executablePath:
    process.env.CHROME_PATH ||
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: true,
});
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
await page.goto(process.env.BIOTWIN_TEST_URL || "http://localhost:8000");
// The what-if lab that used to drive this measurement is gone; the animated
// twin on the overview is what actually costs frames now.
await page
  .locator(".twin-hero canvas, .twin-hero .coach-portrait img")
  .first()
  .waitFor();
console.log("Measuring 60 seconds of the animated twin at desktop resolution.");
const stats = await page.evaluate(
  () =>
    new Promise((resolve) => {
      const samples = [];
      const start = performance.now();
      let previous = start;
      function tick(now) {
        if (now - start > 2500) samples.push(now - previous);
        previous = now;
        if (now - start < 62500) {
          requestAnimationFrame(tick);
          return;
        }
        samples.sort((a, b) => a - b);
        resolve({
          frames: samples.length,
          p50: samples[Math.floor(samples.length * 0.5)],
          p95: samples[Math.floor(samples.length * 0.95)],
          p99: samples[Math.floor(samples.length * 0.99)],
          max: samples.at(-1),
        });
      }
      requestAnimationFrame(tick);
    }),
);
await page.screenshot({
  path: "test-results/exercise-gesture.png",
  fullPage: true,
});
await writeFile(
  "test-results/performance.json",
  JSON.stringify(stats, null, 2),
);
console.log(JSON.stringify(stats));
await browser.close();
if (stats.p95 >= 20) process.exitCode = 1;
