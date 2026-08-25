import { expect, test } from "@playwright/test";

import {
  CONVERSATION_ID,
  EVIDENCE_RECORD_ID,
  installApiStubs,
  SCHEDULE_RUN_ID,
  SCENARIO_ID,
} from "./support/apiStubs";

test("completes draft, run, reconnect, comparison, and exact evidence targeting", async ({ page }) => {
  test.setTimeout(180_000);
  await installApiStubs(page);
  const chatUrl = `/scenarios/${SCENARIO_ID}?conversation=${CONVERSATION_ID}`;
  await page.goto(chatUrl);

  const evidence = page.getByRole("button", {
    name: new RegExp(`Evidence: demand ${EVIDENCE_RECORD_ID}`),
  });
  await evidence.click();
  const evidenceTarget = page.getByRole("region", {
    name: new RegExp(`Evidence target: Demand ${EVIDENCE_RECORD_ID}`),
  });
  await expect(evidenceTarget).toBeFocused();
  expect(new URL(page.url()).searchParams.get("record")).toBe(EVIDENCE_RECORD_ID);
  await page.getByRole("button", { name: "Return to claim" }).click();
  await expect(page).toHaveURL(chatUrl);
  await expect(evidence).toBeFocused();

  await page.getByRole("textbox", { name: "Message" }).fill("Create a reversible repair draft.");
  await page.getByRole("button", { name: "Send" }).click();
  const draft = page.getByRole("region", { name: "Draft proposal" });
  await expect(draft).toContainText("Draft — no baseline change");
  await expect(draft).toContainText("One reversible repair constraint; no baseline change.");
  await expect(draft).toContainText("Outbound demand interval");
  await expect(draft).toContainText(EVIDENCE_RECORD_ID);

  await draft.getByRole("button", { name: "Run optimization" }).click();
  const queued = draft.getByRole("status", { name: "Optimization queued" });
  await expect(queued).toContainText(SCHEDULE_RUN_ID);
  await expect(queued).toContainText("solver_queued");

  await page.getByRole("link", { name: "Runs" }).click();
  const row = page.getByRole("row").filter({ hasText: SCHEDULE_RUN_ID });
  await expect(row).toContainText("In progress");
  await expect(row.getByRole("button", { name: `Copy Run ID ${SCHEDULE_RUN_ID}` })).toBeVisible();
  await row.getByRole("link", { name: "View progress" }).click();

  const runUrl = `/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`;
  await expect(page).toHaveURL(runUrl);
  await expect(page.getByRole("heading", { name: "Results" })).toBeVisible();
  await expect(page.getByText("In progress", { exact: true })).toBeVisible();
  await expect(page.getByText("Accepted 2026-08-25 01:00", { exact: true })).toBeVisible();

  await page.reload();
  await expect(page).toHaveURL(runUrl);
  await expect(page.getByText("In progress", { exact: true })).toBeVisible();

  await page.getByRole("button", { name: "Refresh" }).click();
  await expect(page.getByRole("heading", { name: "Candidate comparison" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Metric deltas" })).toBeVisible();
  await expect(page.getByText("Coverage served delta").locator("..")).toContainText("120.00");
  await expect(page.getByRole("heading", { name: "Candidate schedule" }).locator("..")).toContainText("worker:0 · pick · minutes 2880–3360");
  await expect(page.getByRole("heading", { name: "Evidence" }).locator("..")).toContainText(`demand: ${EVIDENCE_RECORD_ID}`);
});
