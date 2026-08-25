import { expect, test, type Locator, type Page } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import {
  CONVERSATION_ID,
  installApiStubs,
  SCHEDULE_RUN_ID,
  SCENARIO_ID,
} from "./support/apiStubs";

// Reused from keyboard-journey.spec.ts so the repair surfaces follow the same
// visible-focus convention as the established Gate A keyboard suite.
async function expectKeyboardFocus(locator: Locator) {
  await expect(locator).toBeFocused();
  expect(await locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return style.boxShadow !== "none" || style.outlineStyle !== "none";
  })).toBe(true);
}

async function tabTo(page: Page, locator: Locator, limit = 500) {
  for (let index = 0; index < limit; index += 1) {
    if (await locator.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press("Tab");
  }
  throw new Error(`Keyboard focus did not reach ${await locator.getAttribute("aria-label") ?? await locator.textContent()}`);
}

test("keeps repair Chat, Runs, and Results axe-clean, keyboard-operable, and semantically literal", async ({ page }) => {
  test.setTimeout(180_000);
  await installApiStubs(page);
  await page.goto(`/scenarios/${SCENARIO_ID}?conversation=${CONVERSATION_ID}`);

  const composer = page.getByRole("textbox", { name: "Message" });
  await composer.fill("Create a reversible repair draft.");
  const send = page.getByRole("button", { name: "Send" });
  await tabTo(page, send);
  await expectKeyboardFocus(send);
  await page.keyboard.press("Enter");

  const draft = page.getByRole("region", { name: "Draft proposal" });
  await expect(draft).toContainText("One reversible repair constraint; no baseline change.");
  const runOptimization = draft.getByRole("button", { name: "Run optimization" });
  await tabTo(page, runOptimization);
  await expectKeyboardFocus(runOptimization);
  await expectAxeClean(page);
  await page.keyboard.press("Enter");
  await expect(draft.getByRole("status", { name: "Optimization queued" })).toContainText(SCHEDULE_RUN_ID);

  const runsLink = page.getByRole("link", { name: "Runs" });
  await tabTo(page, runsLink);
  await expectKeyboardFocus(runsLink);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Runs" })).toBeVisible();
  await expect(runsLink).toBeFocused();

  const runsRegion = page.getByRole("region", { name: "Runs" });
  for (const literal of ["In progress", "Completed", "Infeasible", "Timed out", "Cancelled", "Failed"]) {
    await expect(runsRegion.getByText(literal, { exact: true })).toBeVisible();
  }
  const terminalRow = page.getByRole("row").filter({ hasText: "Timed out" });
  const viewResults = terminalRow.getByRole("link", { name: "View results" });
  const retry = terminalRow.getByRole("button", { name: "Retry" });
  await tabTo(page, viewResults);
  await expectKeyboardFocus(viewResults);
  await tabTo(page, retry);
  await expectKeyboardFocus(retry);
  await expectAxeClean(page);

  const runningRow = page.getByRole("row").filter({ hasText: SCHEDULE_RUN_ID });
  const viewProgress = runningRow.getByRole("link", { name: "View progress" });
  await tabTo(page, viewProgress);
  await expectKeyboardFocus(viewProgress);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(`/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`);
  await expect(page.getByText("In progress", { exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.activeElement !== document.body)).toBe(true);
  await expectAxeClean(page);

  const refresh = page.getByRole("button", { name: "Refresh" });
  await tabTo(page, refresh);
  await expectKeyboardFocus(refresh);
  await page.keyboard.press("Enter");
  await expect(page.getByText("In progress", { exact: true })).toBeVisible();
  await tabTo(page, refresh);
  await expectKeyboardFocus(refresh);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Candidate comparison" })).toBeVisible();
  await expect(page.getByText("demand: outbound:0", { exact: true })).toBeVisible();
  await expectAxeClean(page);
});
