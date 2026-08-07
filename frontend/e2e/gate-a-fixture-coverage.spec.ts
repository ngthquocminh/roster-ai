import { expect, test } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { installApiStubs, SCENARIO_ID } from "./support/apiStubs";

// Story 1.10 governs two Gate A fixtures (evidence/story-1.10/...json's version_bindings), but the
// rest of this story's harness only ever loads sample_tiny_input.projection-v1.json. The two
// fixtures are identical except sample_tiny_input_more_tm.projection-v1.json's workers group has
// 22 rows instead of 10 (everything else byte-identical) — so this exercises the one group where
// the second fixture actually produces a denser, distinct table, closing that coverage gap.
test("keeps the workers table axe-clean and contained-scroll intact with a denser dataset (more team members fixture)", async ({ page }) => {
  await installApiStubs(page, { fixture: "more_tm" });
  await page.goto(`/scenarios/${SCENARIO_ID}/data?group=workers`);
  await expect(page.getByRole("heading", { level: 2, name: "Scenario Data" })).toBeVisible();

  const status = page.getByRole("status").filter({ hasText: "Showing" });
  await expect(status).toContainText("22");

  const region = page.getByRole("region", { name: "Workers" });
  const overflowsVertically = await region.evaluate((element) => element.scrollHeight > element.clientHeight);
  expect(overflowsVertically).toBe(true);

  // The AC constraint is no *page-level horizontal* scroll (the table region owns its own scroll
  // instead) — page-level vertical scroll from surrounding chrome (heading, filters) is expected
  // and out of scope here; see layout-accessibility.spec.ts for the established assertion shape.
  const documentWidth = await page.evaluate(() => ({
    client: document.documentElement.clientWidth,
    scroll: document.documentElement.scrollWidth,
  }));
  expect(documentWidth.scroll).toBeLessThanOrEqual(documentWidth.client);

  await expectAxeClean(page);
});
