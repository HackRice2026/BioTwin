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
  viewport: { width: 1440, height: 1050 },
});
const report = {
  errors: [],
  layouts: [],
  pwa: false,
  offline: false,
  forecast: false,
  calendar: false,
};
await mkdir("test-results", { recursive: true });
const page = await context.newPage();
page.on("pageerror", (e) => report.errors.push(e.message));
try {
  await page.goto(root);
  await page.locator(".twin-hero canvas").waitFor();
  await page.evaluate(() => document.fonts.ready);
  for (const viewport of [
    { width: 1440, height: 1050 },
    { width: 390, height: 844 },
    { width: 360, height: 740 },
    { width: 1024, height: 900 },
  ]) {
    await page.setViewportSize(viewport);
    const nav = page.getByRole("navigation", {
      name: viewport.width <= 760 ? "Mobile navigation" : "Main navigation",
      exact: true,
    });
    for (const name of [
      "Overview",
      "Signals",
      "Daily plan",
      "Connections",
    ]) {
      await nav.getByRole("button", { name, exact: true }).click();
      await page.waitForTimeout(180);
      assert.ok(
        await page
          .getByRole("meter", { name: "Body Battery, measured" })
          .isVisible(),
      );
      assert.equal(
        await page.evaluate(
          () => document.documentElement.scrollWidth > innerWidth,
        ),
        false,
        `${name} overflow at ${viewport.width}`,
      );
      if (name === "Overview" && [390, 1440].includes(viewport.width))
        await page.screenshot({
          path: `test-results/redesign-overview-${viewport.width}.png`,
          fullPage: true,
        });
    }
    report.layouts.push(viewport.width);
  }
  const nav = page.getByRole("navigation", {
    name: "Main navigation",
    exact: true,
  });
  await nav.getByRole("button", { name: "Overview", exact: true }).click();
  // The what-if lab is gone. What has to work instead is the Body Battery
  // broadcast: the tile button opens it, and it renders in whichever state the
  // account's data puts it -- a chart, or the refusal on a stale reading.
  await page
    .getByRole("button", { name: /Battery Broadcast/ })
    .click();
  const broadcast = page.getByRole("dialog", { name: "Battery Broadcast" });
  await broadcast.waitFor();
  assert.ok(await broadcast.getByRole("heading", { name: "Battery Broadcast" }).isVisible());
  await broadcast.getByRole("button", { name: "Close", exact: true }).click();
  await broadcast.waitFor({ state: "hidden" });
  report.forecast = true;
  for (const name of ["Heart rate", "Sleep", "Calories burned", "Steps"]) {
    await page
      .getByRole("button", { name: `Explore ${name}`, exact: true })
      .click();
    await page.getByTestId("topic-takeover").waitFor();
    await page.getByLabel("Back to Overview", { exact: true }).click();
    assert.equal(await page.getByTestId("topic-takeover").count(), 0);
  }
  // Test the calendar UI request contract without writing to an external calendar.
  await context.route("**/api/session", async (route) => {
    const response = await route.fetch();
    await route.fulfill({
      response,
      json: { ...(await response.json()), demo: false },
    });
  });
  const start = new Date(Date.now() + 3600000),
    end = new Date(Date.now() + 5400000);
  await context.route("**/api/plan/today", (route) =>
    route.fulfill({
      json: {
        date: start.toISOString().slice(0, 10),
        timezone: "America/Chicago",
        calendar_status: "connected",
        explanation: "",
        busy: [],
        proposals: [
          {
            id: "verified-proposal",
            kind: "workout",
            title: "A little movement",
            start: start.toISOString(),
            end: end.toISOString(),
            intensity: "light",
            reason: "An available window.",
            score: 1,
            terms: {},
          },
        ],
      },
    }),
  );
  let booked;
  await context.route("**/api/calendar/events", async (route) => {
    booked = route.request().postDataJSON();
    await route.fulfill({ json: { status: "created" } });
  });
  await page.reload();
  await page
    .getByRole("navigation", { name: "Main navigation", exact: true })
    .getByRole("button", { name: "Daily plan", exact: true })
    .click();
  await page.getByLabel("Remind me before an event").selectOption("15");
  await page
    .getByRole("button", {
      name: "Add A little movement to calendar",
      exact: true,
    })
    .click();
  await page
    .getByRole("button", {
      name: "Added A little movement to calendar",
      exact: true,
    })
    .waitFor();
  assert.deepEqual(booked, {
    proposal_id: "verified-proposal",
    reminder_minutes: 15,
  });
  report.calendar = true;
  await context.unrouteAll({ behavior: "wait" });
  await page.reload();
  const manifest = await (
    await context.request.get(`${root}/manifest.webmanifest`)
  ).json();
  assert.equal(manifest.display, "standalone");
  assert.equal(manifest.start_url, "/");
  assert.ok(manifest.icons.some((i) => i.sizes === "192x192"));
  assert.ok(
    manifest.icons.some(
      (i) => i.sizes === "512x512" && i.purpose === "maskable",
    ),
  );
  for (const icon of manifest.icons)
    assert.equal(
      (await context.request.get(new URL(icon.src, root).href)).status(),
      200,
    );
  assert.equal(
    await page.locator('link[rel="apple-touch-icon"]').getAttribute("href"),
    "/apple-touch-icon.png",
  );
  await page.evaluate(() => navigator.serviceWorker.ready);
  await page.waitForFunction(() => !!navigator.serviceWorker.controller);
  report.pwa = true;
  const privateCached = await page.evaluate(async () => {
    const urls = (
      await Promise.all(
        (await caches.keys()).map(async (k) =>
          (await (await caches.open(k)).keys()).map((r) => r.url),
        ),
      )
    ).flat();
    return urls.filter((u) => new URL(u).pathname.startsWith("/api/"));
  });
  assert.deepEqual(privateCached, []);
  await context.setOffline(true);
  await page.reload();
  await page
    .getByText(
      "You're viewing an offline example. Your personal measurements aren't updating.",
      { exact: false },
    )
    .waitFor({ timeout: 20000 });
  await page.locator(".twin-hero canvas").waitFor();
  assert.equal(await page.locator(".canvas-fallback").count(), 0);
  await page.setViewportSize({ width: 390, height: 844 });
  await page
    .getByRole("navigation", { name: "Mobile navigation", exact: true })
    .getByRole("button", { name: "Signals", exact: true })
    .click();
  await page.waitForTimeout(200);
  await page.screenshot({
    path: "test-results/redesign-offline.png",
    fullPage: true,
  });
  report.offline = true;
  assert.deepEqual(report.errors, []);
  console.log(JSON.stringify(report));
  await writeFile(
    "test-results/redesign-browser-report.json",
    JSON.stringify(report, null, 2),
  );
} catch (error) {
  await page.screenshot({
    path: "test-results/redesign-browser-failure.png",
    fullPage: true,
  });
  throw error;
} finally {
  await browser.close();
}
