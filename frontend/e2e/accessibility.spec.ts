import { expect, test } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { installApiStubs, SCENARIO_ID } from "./support/apiStubs";

// Filter values are real IDs/enum values from data/contract/sample_tiny_input.projection-v1.json
// (not placeholders) so apiStubs.ts's filter matching renders a genuinely filtered, non-empty
// table — proving the "filter applied" state, not just re-scanning the unfiltered one.
// baseline-assignments and locks are empty in this fixture regardless of filter.
const groups = [
  ["overview", ""],
  ["work-areas-and-tasks", "&task_id=1E5596F1-C9AD-43F1-8DC4-7CF8013C9D0B"],
  ["workers", "&contact_id=DF47249E-8864-41B6-93CB-004100655A58"],
  ["demand", "&family=outbound"],
  ["baseline-assignments", "&worker_id=worker-1"],
  ["locks", "&target_type=assignment"],
  ["constraints-and-objectives", "&constraint_type=ShiftStartTime"],
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
      // The menu-scoped scan above only covers the chooser itself. Re-scan the whole page so the
      // table region that actually lost a column — the part the "column hidden" state is meant to
      // exercise — is axe-clean too, not just assumed clean because the pre-hide scan passed.
      await expectAxeClean(page);
    }
  });
}
