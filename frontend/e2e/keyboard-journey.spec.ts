import { expect, test, type Locator, type Page } from "@playwright/test";

import { installApiStubs } from "./support/apiStubs";

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
    origin: "http://localhost:4173",
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
  await page.keyboard.press("End");
  await page.keyboard.press("Enter");
  const apply = page.getByRole("button", { name: "Apply" });
  await tabTo(page, apply);
  await expectKeyboardFocus(apply);
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/family=indirect/);

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
