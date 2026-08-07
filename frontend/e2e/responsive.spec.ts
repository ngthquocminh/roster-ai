import { expect, test } from "@playwright/test";

import { installApiStubs, SCENARIO_ID } from "./support/apiStubs";

const demandUrl = `/scenarios/${SCENARIO_ID}/data?group=demand`;

test.beforeEach(async ({ page }) => {
  await installApiStubs(page);
});

test("uses the full-width desktop workspace and a horizontal control cluster", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.goto(demandUrl);
  await expect(page.getByRole("region", { name: "Demand" })).toBeVisible();

  await expect(page.getByRole("columnheader")).toHaveCount(7);
  const filter = await page.getByRole("region", { name: "Filter records" }).boundingBox();
  const chooser = await page.getByRole("button", { name: "Choose columns" }).boundingBox();
  expect(filter).not.toBeNull();
  expect(chooser).not.toBeNull();
  expect(Math.abs(filter!.y - chooser!.y)).toBeLessThan(8);
  expect(chooser!.x).toBeGreaterThan(filter!.x);
});

test("stacks controls at the fixed tablet breakpoint", async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 1024 });
  await page.goto(demandUrl);
  await expect(page.getByRole("region", { name: "Demand" })).toBeVisible();

  const filter = await page.getByRole("region", { name: "Filter records" }).boundingBox();
  const chooser = await page.getByRole("button", { name: "Choose columns" }).boundingBox();
  expect(filter).not.toBeNull();
  expect(chooser).not.toBeNull();
  expect(filter!.y).toBeGreaterThan(chooser!.y + chooser!.height);
});

test("uses an overridable essential-column phone default", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(demandUrl);
  await expect(page.getByRole("region", { name: "Demand" })).toBeVisible();

  await expect(page.getByRole("columnheader")).toHaveText([
    "Record ID",
    "Family",
    "Window",
    "Amount",
    "Unit",
  ]);
  await expect(page.getByText(/Create draft|Run scenario|Cancel run|Approve baseline/i)).toHaveCount(0);

  await page.getByRole("button", { name: "Choose columns" }).click();
  await page.getByRole("menuitemcheckbox", { name: "Task ID" }).click();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("columnheader", { name: "Task ID" })).toBeVisible();
  await page.reload();
  await expect(page.getByRole("columnheader", { name: "Task ID" })).toBeVisible();
});

test("lets an evidence target override the phone default and locks the field", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${demandUrl}&field=task_id`);

  await expect(page.getByRole("columnheader", { name: "Task ID" })).toBeVisible();
  await expect(page.getByText("Task ID is shown because an evidence link targets it.")).toBeVisible();
  await page.getByRole("button", { name: "Choose columns" }).click();
  await expect(page.getByRole("menuitemcheckbox", { name: /Task ID.*Shown for the linked evidence target/ })).toBeDisabled();
});
