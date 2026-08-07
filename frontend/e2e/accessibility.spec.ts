import { expect, test } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { installApiStubs, SCENARIO_ID } from "./support/apiStubs";

const groups = [
  ["overview", ""],
  ["work-areas-and-tasks", "&task_id=task-1"],
  ["workers", "&contact_id=worker-1"],
  ["demand", "&family=outbound"],
  ["baseline-assignments", "&worker_id=worker-1"],
  ["locks", "&target_type=assignment"],
  ["constraints-and-objectives", "&constraint_type=MaximumHours"],
] as const;

for (const viewport of [
  { name: "desktop", width: 1280, height: 800 },
  { name: "tablet", width: 900, height: 1024 },
  { name: "phone", width: 390, height: 844 },
] as const) {
  test(`runs the complete WCAG axe configuration across Gate A at ${viewport.name}`, async ({ page }) => {
    test.setTimeout(120_000);
    await installApiStubs(page);
    await page.setViewportSize(viewport);

    await page.goto("/");
    await expect(page.getByRole("heading", { level: 1, name: "Fixture catalogue" })).toBeVisible();
    await expectAxeClean(page);

    for (const [group, filter] of groups) {
      await page.goto(`/scenarios/${SCENARIO_ID}/data?group=${group}${filter}`);
      await expect(page.getByRole("heading", { level: 2, name: "Scenario Data" })).toBeVisible();
      await expectAxeClean(page);
      if (group === "overview") continue;

      await page.getByRole("button", { name: "Choose columns" }).click();
      const hideable = page.locator('[role="menuitemcheckbox"][aria-checked="true"]:not([data-disabled])').first();
      if (await hideable.count()) await hideable.click();
      await expectAxeClean(page, '[role="menu"]');
      await page.keyboard.press("Escape");
    }
  });
}
