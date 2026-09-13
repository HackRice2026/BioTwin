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
  viewport: { width: 1440, height: 1100 },
});
await mkdir("test-results", { recursive: true });
const errors = [];
let questionBody,
  eventBody,
  writes = 0,
  reads = 0,
  failRead = false,
  partial = false;
const calendar = {
  id: "primary",
  name: "Personal",
  color: "#8bc5a6",
  primary: true,
  writable: true,
  provider: "google-calendar",
};
const work = {
  ...calendar,
  id: "work",
  name: "Work",
  color: "#88bafa",
  primary: false,
};
const day = new Date().toISOString().slice(0, 10);
const nextDay = new Date(Date.now() + 86400000).toISOString().slice(0, 10);
const items = [
  {
    id: "one",
    title: "Product design review",
    start: `${day}T09:00:00-05:00`,
    end: `${day}T10:00:00-05:00`,
    all_day: false,
    calendar_id: "work",
    calendar_name: "Work",
    color: work.color,
    provider: "google-calendar",
    location: "Design studio",
    description: "Discuss the prototype. <script>not executable</script>",
    recurring: true,
    url: "https://calendar.google.com/",
  },
  {
    id: "two",
    title: "Lunch with Maya",
    start: `${day}T12:30:00-05:00`,
    end: `${day}T13:15:00-05:00`,
    all_day: false,
    calendar_id: "primary",
    calendar_name: "Personal",
    color: calendar.color,
    provider: "google-calendar",
    location: "Rice Village",
  },
  {
    id: "three",
    title: "Project submission",
    start: day,
    end: nextDay,
    all_day: true,
    calendar_id: "work",
    calendar_name: "Work",
    color: work.color,
    provider: "google-calendar",
  },
];
const tasks = [
  {
    id: "t1",
    title: "Send presentation slides",
    due: day,
    list_name: "Work",
    completed: false,
    notes: "Include the updated agenda.",
  },
  {
    id: "t2",
    title: "Read design notes",
    due: null,
    list_name: "Personal",
    completed: false,
    notes: "",
  },
  {
    id: "t3",
    title: "Review proposal",
    due: day,
    list_name: "Work",
    completed: true,
    notes: "",
  },
];
await context.route("**/api/calendar/agenda?*", (route) => {
  reads++;
  const params = new URL(route.request().url()).searchParams;
  if (failRead)
    return route.fulfill({
      status: 502,
      json: { detail: "Your calendar could not refresh." },
    });
  return route.fulfill({
    json: {
      start: params.get("start"),
      end: params.get("end"),
      timezone: "America/Chicago",
      events: items,
      tasks,
      calendars: [calendar, work],
      warnings: partial
        ? [
            "Google Tasks could not be loaded. Check Tasks access in Connections, then try again.",
          ]
        : [],
      status: "connected",
      tasks_status: partial ? "unavailable" : "connected",
      fetched_at: new Date().toISOString(),
    },
  });
});
await context.route("**/api/calendar/drafts", (route) => {
  eventBody = route.request().postDataJSON();
  return route.fulfill({
    json: {
      ...eventBody,
      id: "reviewed-draft",
      calendar_name: "Personal",
      timezone: "America/Chicago",
    },
  });
});
await context.route("**/api/calendar/drafts/*/confirm", (route) => {
  writes++;
  items.push({
    ...eventBody,
    id: "created",
    calendar_name: "Personal",
    color: calendar.color,
    provider: "google-calendar",
    start: `${eventBody.start}:00-05:00`,
    end: `${eventBody.end}:00-05:00`,
  });
  return route.fulfill({ json: { status: "created", id: "created" } });
});
await context.route("**/api/twin/ask", (route) => {
  questionBody = route.request().postDataJSON();
  return route.fulfill({
    json: {
      id: "calendar-chat",
      answer: "I've prepared a draft. Review it before adding it.",
      mode: "language_service",
      voice_configured: false,
      calendar_draft: {
        id: "ai-draft",
        title: "Study session",
        start: `${nextDay}T15:00:00-05:00`,
        end: `${nextDay}T15:30:00-05:00`,
        all_day: false,
        calendar_id: "primary",
        calendar_name: "Personal",
        timezone: "America/Chicago",
        reminder_minutes: 15,
        notes: "",
        location: "",
      },
    },
  });
});
const page = await context.newPage();
page.on("pageerror", (e) => errors.push(e.message));
try {
  await page.goto(`${root}/?connected=google-calendar`);
  await page
    .getByRole("heading", { name: "Your calendar", exact: true })
    .waitFor();
  await page.getByText("Product design review", { exact: true }).waitFor();
  for (const width of [1440, 390, 360]) {
    await page.setViewportSize({ width, height: width < 760 ? 844 : 1100 });
    await page.screenshot({
      path: `test-results/calendar-${width}.png`,
      fullPage: true,
    });
    assert.equal(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
      false,
    );
    assert.ok(
      await page
        .getByRole("meter", { name: "Body Battery estimate" })
        .isVisible(),
    );
  }
  await page.getByText("Product design review", { exact: true }).click();
  await page.getByText("Discuss the prototype.", { exact: false }).waitFor();
  assert.equal(await page.locator(".event-description script").count(), 0);
  await page
    .getByLabel("Filter calendar", { exact: true })
    .selectOption("primary");
  assert.equal(
    await page.getByText("Product design review", { exact: true }).count(),
    0,
  );
  assert.ok(
    await page.getByText("Lunch with Maya", { exact: true }).isVisible(),
  );
  await page.getByLabel("Filter calendar", { exact: true }).selectOption("all");
  await page.getByLabel("Search events and tasks").fill("submission");
  assert.equal(await page.locator(".calendar-event").count(), 1);
  await page.getByLabel("Search events and tasks").fill("");
  assert.equal(await page.locator(".calendar-task").count(), 2);
  await page.getByLabel("Filter tasks").selectOption("all");
  assert.equal(await page.locator(".calendar-task").count(), 3);
  await page.getByRole("button", { name: `Show ${day}`, exact: true }).click();
  await page
    .getByRole("button", { name: "Show all days", exact: true })
    .click();
  const previous = reads;
  await page.getByLabel("Next calendar range").click();
  await page.waitForResponse((r) => r.url().includes("/api/calendar/agenda?"));
  assert.ok(reads > previous);
  await page.getByRole("button", { name: "Today", exact: true }).click();
  await page.getByRole("button", { name: "New event", exact: false }).click();
  const editor = page.getByRole("dialog", { name: "Review calendar event" });
  await editor.waitFor();
  await page
    .getByLabel("Event title", { exact: true })
    .fill("Coffee with the team");
  await page
    .getByLabel("Event start", { exact: true })
    .fill(`${nextDay}T10:00`);
  await page.getByLabel("Event end", { exact: true }).fill(`${nextDay}T10:30`);
  await page.getByLabel("Event reminder", { exact: true }).selectOption("15");
  assert.equal(writes, 0);
  await page.screenshot({ path: "test-results/calendar-editor-mobile.png" });
  await editor
    .getByRole("button", { name: "Add to calendar", exact: true })
    .click();
  await editor.waitFor({ state: "detached" });
  assert.equal(writes, 1);
  assert.equal(eventBody.reminder_minutes, 15);
  await page.getByText("Coffee with the team", { exact: true }).waitFor();
  await page
    .getByLabel("Ask about your calendar")
    .fill("Add a study session tomorrow at 3 pm for 30 minutes");
  await page.getByLabel("Ask calendar question", { exact: true }).click();
  await editor.waitFor();
  assert.equal(
    await page.getByLabel("Event title", { exact: true }).inputValue(),
    "Study session",
  );
  assert.equal(writes, 1, "AI draft must not write an event");
  assert.equal(questionBody.calendar_mode, true);
  assert.ok(questionBody.calendar_start && questionBody.calendar_end);
  await page.keyboard.press("Escape");
  await editor.waitFor({ state: "detached" });
  partial = true;
  await page.getByLabel("Refresh calendar events").click();
  await page
    .getByText("Google Tasks could not be loaded.", { exact: false })
    .waitFor();
  assert.ok(
    await page.getByText("Product design review", { exact: true }).isVisible(),
  );
  failRead = true;
  await page.getByLabel("Refresh calendar events").click();
  await page
    .getByRole("alert")
    .filter({ hasText: "Your calendar could not refresh" })
    .waitFor();
  assert.equal(
    await page.locator(".calendar-event").count(),
    0,
    "Do not present a failed refresh as current data",
  );
  assert.deepEqual(errors, []);
  const report = {
    errors,
    layouts: [1440, 390, 360],
    namedEvents: true,
    filters: true,
    tasks: true,
    eventDraftReview: true,
    writeThenRefresh: true,
    aiDraftNoWrite: true,
    partialFailure: true,
  };
  await writeFile(
    "test-results/calendar-report.json",
    JSON.stringify(report, null, 2),
  );
  console.log(JSON.stringify(report));
} catch (e) {
  await page.screenshot({
    path: "test-results/calendar-failure.png",
    fullPage: true,
  });
  throw e;
} finally {
  await browser.close();
}
