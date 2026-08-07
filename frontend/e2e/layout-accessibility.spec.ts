import { expect, test, type Locator, type Page } from "@playwright/test";

import { installApiStubs, SCENARIO_ID } from "./support/apiStubs";

const demandUrl = `/scenarios/${SCENARIO_ID}/data?group=demand`;

test.describe.configure({ timeout: 120_000 });

async function expectMinimumTarget(locator: Locator, label: string) {
  const box = await locator.boundingBox();
  expect(box, `${label} must render`).not.toBeNull();
  expect(box!.width, `${label} width`).toBeGreaterThanOrEqual(44);
  expect(box!.height, `${label} height`).toBeGreaterThanOrEqual(44);
}

async function openDemand(page: Page, viewport = { width: 1280, height: 800 }) {
  await page.setViewportSize(viewport);
  await page.goto(demandUrl);
  await expect(page.getByRole("region", { name: "Demand" })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await installApiStubs(page);
});

test("keeps sort and column-menu targets at least 44 by 44 CSS pixels", async ({ page }) => {
  await openDemand(page);
  for (const button of await page.getByRole("button", { name: /^Sort by / }).all()) {
    await expectMinimumTarget(button, await button.getAttribute("aria-label") ?? "sort button");
  }

  await page.getByRole("button", { name: "Choose columns" }).click();
  for (const item of await page.getByRole("menuitemcheckbox").all()) {
    await expectMinimumTarget(item, `column item ${await item.textContent()}`);
  }
});

for (const viewport of [
  { name: "desktop", width: 1280, height: 800 },
  { name: "tablet", width: 900, height: 1024 },
  { name: "phone", width: 390, height: 844 },
] as const) {
  test(`contains horizontal overflow and keeps an opaque sticky header at ${viewport.name}`, async ({ page }) => {
    await openDemand(page, viewport);
    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);

    const region = page.getByRole("region", { name: "Demand" });
    const regionDimensions = await region.evaluate((element) => ({
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
      tabIndex: element.tabIndex,
    }));
    if (viewport.name === "desktop") {
      expect(regionDimensions.scrollWidth).toBeGreaterThanOrEqual(regionDimensions.clientWidth);
    } else {
      expect(regionDimensions.scrollWidth).toBeGreaterThan(regionDimensions.clientWidth);
    }
    expect(regionDimensions.tabIndex).toBe(0);

    const headerAlpha = await region.locator("thead").evaluate((element) => {
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const context = canvas.getContext("2d")!;
      context.fillStyle = getComputedStyle(element).backgroundColor;
      context.fillRect(0, 0, 1, 1);
      return context.getImageData(0, 0, 1, 1).data[3];
    });
    expect(headerAlpha).toBe(255);
  });

  test(`keeps every Scenario Data action at least 44 by 44 at ${viewport.name}`, async ({ page }) => {
    await openDemand(page, viewport);
    const actions = page.locator('[aria-labelledby="scenario-data-heading"] button:not(:disabled), [aria-labelledby="scenario-data-heading"] input, [aria-labelledby="scenario-data-heading"] [role="combobox"], [aria-labelledby="scenario-data-heading"] [role="tab"]');
    for (const action of await actions.all()) {
      await expectMinimumTarget(action, await action.getAttribute("aria-label") ?? await action.textContent() ?? "Scenario Data action");
    }
  });
}

test("reflows at the 200 percent zoom-equivalent viewport without page overflow", async ({ page }) => {
  await openDemand(page, { width: 640, height: 400 });
  const documentWidth = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(documentWidth.scroll).toBeLessThanOrEqual(documentWidth.client);
  await expect(page.getByRole("button", { name: "Choose columns" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply" })).toBeVisible();
  await expect(page.getByRole("status").filter({ hasText: "Showing" })).not.toBeEmpty();
});

test("contains the widest table at 320 CSS pixels", async ({ page }) => {
  await openDemand(page, { width: 320, height: 640 });
  const widths = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);
  const region = page.getByRole("region", { name: "Demand" });
  expect(await region.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
});

test("survives WCAG text spacing without clipping, overlap, or page overflow", async ({ page }) => {
  await openDemand(page, { width: 390, height: 844 });
  await page.addStyleTag({ content: `
    * { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
    p { margin-bottom: 2em !important; }
  ` });
  const widths = await page.evaluate(() => ({ client: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client);

  const actions = page.locator('[aria-labelledby="scenario-data-heading"] button:not(:disabled), [aria-labelledby="scenario-data-heading"] input, [aria-labelledby="scenario-data-heading"] [role="combobox"]');
  for (const action of await actions.all()) {
    await action.scrollIntoViewIfNeeded();
    const hit = await action.evaluate((element) => {
      const box = element.getBoundingClientRect();
      const top = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
      return box.width > 0 && box.height > 0 && (top === element || element.contains(top));
    });
    expect(hit, await action.getAttribute("aria-label") ?? await action.textContent() ?? "action").toBe(true);
  }
});
