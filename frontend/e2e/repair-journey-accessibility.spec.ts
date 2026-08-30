import { expect, test, type Locator, type Page } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import {
  CONVERSATION_ID,
  installApiStubs,
  SCHEDULE_RUN_ID,
  SCENARIO_ID,
  TIMED_OUT_RUN_ID,
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
  const journey = await installApiStubs(page);
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
  // Route entry must move focus into the new view rather than dropping it on
  // <body> when the link that was focused unmounts. Assert WHERE focus landed,
  // not merely that it is somewhere: `!== document.body` also passes if focus
  // is left on an arbitrary element.
  await expect(page.getByRole("heading", { name: "Results" })).toBeFocused();
  await expectAxeClean(page);

  const refresh = page.getByRole("button", { name: "Refresh" });
  await tabTo(page, refresh);
  await expectKeyboardFocus(refresh);
  await page.keyboard.press("Enter");
  // "In progress" is already on screen, so a bare toBeVisible() passes on its
  // first poll before the refetch resolves. Wait for the read to complete
  // (the button re-enables) so this actually observes the refetched state.
  await expect(refresh).toBeEnabled();
  await expect(page.getByText("In progress", { exact: true })).toBeVisible();

  journey.completeRun();
  await tabTo(page, refresh);
  await expectKeyboardFocus(refresh);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Candidate comparison" })).toBeVisible();
  await expect(page.getByText("demand: outbound:0", { exact: true })).toBeVisible();
  await expectAxeClean(page);

  // The terminal branch is a distinct render path with its own literal text
  // (AC2's "semantic status text"); scan it too rather than only its Runs-table badge.
  await page.goto(`/scenarios/${SCENARIO_ID}/runs/${TIMED_OUT_RUN_ID}`);
  const outcome = page.getByRole("region", { name: "Run outcome" });
  await expect(outcome).toContainText("Solver ceiling reached");
  await expect(page.getByRole("heading", { name: "Results" })).toBeFocused();
  await expectAxeClean(page);
});

test("keeps the approval dialog named and restores focus at 100 and 200 percent zoom", async ({ page }) => {
  test.setTimeout(120_000);
  const journey = await installApiStubs(page);
  journey.completeRun();
  const approvalId = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
  const approval = {
    approval_id: approvalId, state: "pending", schedule_run_id: SCHEDULE_RUN_ID,
    candidate_schedule_version_id: "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb",
    baseline_schedule_version: null, scenario_version_id: "cccccccc-3333-4333-8333-cccccccccccc",
    consequence_summary: "Candidate replaces no current baseline.", policy_version: "policy-v1",
    agent_run_id: null,
    created_at: "2026-08-29T00:00:00Z", expires_at: "2099-08-29T01:00:00Z", resource_version: 1,
  };
  await page.route("**/api/v1/approvals**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname.endsWith(`/${approvalId}`)) return route.fulfill({ json: approval });
    if (url.pathname.endsWith("/approvals")) return route.fulfill({ json: { items: [approval] } });
    return route.fallback();
  });
  await page.emulateMedia({ reducedMotion: "reduce" });

  for (const width of [1280, 640]) {
    await page.setViewportSize({ width, height: 800 });
    await page.goto(`/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`);
    const trigger = page.getByRole("button", { name: "Approve as baseline" });
    await expect(trigger).toBeVisible();
    await trigger.click();
    await expect(page.getByRole("dialog", { name: "Approve candidate as baseline" })).toBeVisible();
    await expect(page.getByRole("button", { name: /Approve candidate .* replacing no current baseline/ })).toBeVisible();
    await expectAxeClean(page);
    await page.keyboard.press("Escape");
    await expect(trigger).toBeFocused();
    await trigger.click();
    await page.getByRole("button", { name: "Cancel" }).click();
    await expect(trigger).toBeFocused();
  }
});
