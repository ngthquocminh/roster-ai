import { expect, test } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { installApiStubs, SCENARIO_ID, SCHEDULE_RUN_ID } from "./support/apiStubs";

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

// The full WCAG axe configuration over the approval REVIEW surface. The repair
// journey spec covers the dialog's naming and focus return; this covers the
// panel's three states in the same configuration the rest of Gate A is held to,
// including the terminal state, which has no interactive control at all and so
// is the one most likely to regress into colour-only meaning.
for (const [name, state, expectedText] of [
  ["pending", "pending", "Approve as baseline"],
  ["presented-expired", "pending-overdue", "Dismiss expired request"],
  ["terminal", "rejected", "Terminal approval state: rejected"],
  ["post-promotion-terminal", "consumed", "promoted bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb replacing baseline-v12"],
] as const) {
  test(`keeps the ${name} approval review surface axe-clean`, async ({ page }) => {
    test.setTimeout(120_000);
    const journey = await installApiStubs(page);
    journey.completeRun();
    const approvalId = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
    const overdue = state === "pending-overdue";
    const approval = {
      approval_id: approvalId,
      state: overdue ? "pending" : state,
      schedule_run_id: SCHEDULE_RUN_ID,
      candidate_schedule_version_id: "bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb",
      baseline_schedule_version: "baseline-v12",
      scenario_version_id: "cccccccc-3333-4333-8333-cccccccccccc",
      consequence_summary: "Candidate replaces baseline-v12.",
      policy_version: "policy-v1",
      agent_run_id: null,
      created_at: "2026-08-29T00:00:00Z",
      expires_at: overdue ? "2020-01-01T00:00:00Z" : "2099-08-29T01:00:00Z",
      resource_version: 1,
    };
    await page.route("**/api/v1/approvals**", async (route) => {
      const url = new URL(route.request().url());
      if (url.pathname.endsWith(`/${approvalId}`)) return route.fulfill({ json: approval });
      if (url.pathname.endsWith("/approvals")) return route.fulfill({ json: { items: [approval] } });
      return route.fallback();
    });

    await page.goto(`/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`);
    await expect(page.getByText(expectedText)).toBeVisible();
    await expect(page.getByRole("button", { name: "Refresh" })).toBeEnabled();
    // Scoped to the review surface, the way the column-chooser scan above is
    // scoped to its menu. The enclosing Results page carries a pre-existing
    // outline-button contrast violation on its own Refresh control
    // (`deferred-work.md`), which is not this story's and would otherwise mask
    // every result here.
    await expectAxeClean(page, "[data-approval-panel]");
  });
}

for (const zoom of [100, 200] as const) {
  test(`keeps decision provenance axe-clean, inspectable, and contained at ${zoom}% zoom`, async ({ page }) => {
    test.setTimeout(120_000);
    const journey = await installApiStubs(page);
    journey.completeRun();
    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto(`/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`);
    if (zoom === 200) await page.evaluate(() => { document.documentElement.style.zoom = "2"; });

    const provenance = page.getByRole("region", { name: "Decision provenance" });
    await expect(provenance).toBeVisible();
    await expect(provenance.getByRole("list", { name: "Decision provenance" })).toBeVisible();
    await expect(provenance.getByText("Approval decision: approval_consumed")).toBeVisible();
    await expectAxeClean(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);

    const details = provenance.getByRole("button", { name: "Details" });
    await expect(details).toHaveAttribute("aria-expanded", "false");
    await details.click();
    await expect(details).toHaveAttribute("aria-expanded", "true");
    await expect(provenance.getByText("Approval was consumed and the candidate became the baseline.")).toBeVisible();
    await expectAxeClean(page);
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true);
  });
}
