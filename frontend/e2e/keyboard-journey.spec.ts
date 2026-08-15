import { expect, test, type Locator, type Page } from "@playwright/test";

import { CONVERSATION_ID, EVIDENCE_RECORD_ID, installApiStubs, SCENARIO_ID } from "./support/apiStubs";

async function expectKeyboardFocus(locator: Locator) {
  await expect(locator).toBeFocused();
  expect(await locator.evaluate((element) => {
    const style = getComputedStyle(element);
    return style.boxShadow !== "none" || style.outlineStyle !== "none";
  })).toBe(true);
}

async function tabTo(page: Page, locator: Locator, reverse = false, limit = 500) {
  for (let index = 0; index < limit; index += 1) {
    if (await locator.evaluate((element) => element === document.activeElement)) return;
    await page.keyboard.press(reverse ? "Shift+Tab" : "Tab");
  }
  throw new Error(`Keyboard focus did not reach ${await locator.getAttribute("aria-label") ?? await locator.textContent()}`);
}

test("completes the Gate A Scenario Data journey with keyboard only", async ({ context, page }) => {
  test.setTimeout(180_000);
  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    // Must match playwright.config.ts's baseURL — a permission granted to a different origin
    // than the one the page actually loads from is silently never applied.
    origin: "http://127.0.0.1:4173",
  });
  await installApiStubs(page);
  await page.goto("/");

  const catalogueLink = page.getByRole("link", { name: "sample_tiny_input" });
  await tabTo(page, catalogueLink);
  await expectKeyboardFocus(catalogueLink);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 1, name: "sample_tiny_input" })).toBeFocused();

  const dataLink = page.getByRole("link", { name: "Scenario Data" });
  await tabTo(page, dataLink);
  await expectKeyboardFocus(dataLink);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { level: 2, name: "Scenario Data" })).toBeVisible();

  const overviewTab = page.getByRole("tab", { name: "Overview" });
  await tabTo(page, overviewTab);
  await expectKeyboardFocus(overviewTab);
  for (const name of ["Work areas and tasks", "Workers", "Demand"]) {
    await page.keyboard.press("ArrowRight");
    const selectedTab = page.getByRole("tab", { name });
    await expect(selectedTab).toHaveAttribute("aria-selected", "true");
    await expectKeyboardFocus(selectedTab);
  }
  const demandTab = page.getByRole("tab", { name: "Demand" });
  await expectKeyboardFocus(demandTab);
  await expect(page).toHaveURL(/group=demand/);

  const familySort = page.getByRole("button", { name: "Sort by Family" });
  await tabTo(page, familySort);
  await expectKeyboardFocus(familySort);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/sort=family/);

  const familyFilter = page.getByRole("combobox", { name: "Family" });
  await tabTo(page, familyFilter, true);
  await expectKeyboardFocus(familyFilter);
  await page.keyboard.press("Space");
  // "Home" selects the first option ("outbound", 493 rows in the fixture) rather than "End"
  // ("indirect", only 6 rows) — apiStubs.ts now honors the filter for real, and the journey below
  // needs a genuine next page to exist after filtering, not just before it.
  await page.keyboard.press("Home");
  await page.keyboard.press("Enter");
  const apply = page.getByRole("button", { name: "Apply" });
  await tabTo(page, apply);
  await expectKeyboardFocus(apply);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/family=outbound/);

  const next = page.getByRole("button", { name: "Next" });
  await tabTo(page, next);
  await expectKeyboardFocus(next);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/cursor=50/);

  const copy = page.getByRole("button", { name: /^Copy / }).last();
  await tabTo(page, copy, true);
  await expectKeyboardFocus(copy);
  await page.keyboard.press("Enter");
  await expect(page.getByRole("status").filter({ hasText: /^Copied / })).not.toBeEmpty();

  const chooser = page.getByRole("button", { name: "Choose columns" });
  await tabTo(page, chooser);
  await expectKeyboardFocus(chooser);
  await page.keyboard.press("Enter");
  const familyItem = page.getByRole("menuitemcheckbox", { name: "Family" });
  await expect(familyItem).toBeFocused();
  await page.keyboard.press("Space");
  await page.keyboard.press("Escape");
  await expect(chooser).toBeFocused();
  await expect(page.getByRole("columnheader", { name: "Family" })).toHaveCount(0);
  expect(await page.evaluate(() => document.activeElement !== document.body)).toBe(true);
});

test("jumps to exact evidence and returns to the invoking link with keyboard only", async ({ page }) => {
  await installApiStubs(page);
  await page.goto(`/scenarios/${SCENARIO_ID}?conversation=${CONVERSATION_ID}`);

  const evidence = page.getByRole("button", { name: new RegExp(`Evidence: demand ${EVIDENCE_RECORD_ID}`) });
  await tabTo(page, evidence);
  await expectKeyboardFocus(evidence);
  await page.keyboard.press("Enter");

  // The region names the group with its planner-facing label ("Demand"), the
  // same string the tab uses — not the URL slug.
  const target = page.getByRole("region", { name: new RegExp(`Evidence target: Demand ${EVIDENCE_RECORD_ID}`) });
  await expectKeyboardFocus(target);
  await expect(page).toHaveURL(new RegExp(`/scenarios/${SCENARIO_ID}/data\\?`));
  expect(new URL(page.url()).searchParams.get("record")).toBe(EVIDENCE_RECORD_ID);

  const returnToClaim = page.getByRole("button", { name: "Return to claim" });
  await tabTo(page, returnToClaim);
  await expectKeyboardFocus(returnToClaim);
  await page.keyboard.press("Enter");

  await expect(page).toHaveURL(`/scenarios/${SCENARIO_ID}?conversation=${CONVERSATION_ID}`);
  await expectKeyboardFocus(evidence);
});
