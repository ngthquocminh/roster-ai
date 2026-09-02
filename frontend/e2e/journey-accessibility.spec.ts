import { expect, test, type Page } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { CONVERSATION_ID, installApiStubs, SCENARIO_ID, SCHEDULE_RUN_ID } from "./support/apiStubs";

// Each route is paired with the readiness anchor that proves it finished rendering.
// Without one, `page.goto` resolves on `load`, before the stubbed queries settle,
// and every scan measures a 64-character app shell: the code review measured
// `bodyChars: 64` / `focusable: 2` immediately after `goto` against 665 (Chat),
// 1226 (Runs) and 1837 (Results) once settled.
const JOURNEY = [
  {
    url: `/scenarios/${SCENARIO_ID}?conversation=${CONVERSATION_ID}`,
    // Task 6 asks for "Chat (timeline plus draft)", so the anchor is the draft
    // region rather than the page heading — it is the last thing to arrive.
    ready: (page: Page) => expect(page.getByRole("region", { name: "Draft proposal" })).toBeVisible(),
  },
  {
    url: `/scenarios/${SCENARIO_ID}/runs`,
    ready: (page: Page) => expect(page.getByRole("heading", { name: "Runs" })).toBeVisible(),
  },
  {
    url: `/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`,
    ready: (page: Page) => expect(page.getByRole("heading", { name: "Results" })).toBeVisible(),
  },
] as const;

// `layout-accessibility.spec.ts:102-108`'s rule verbatim, paragraph spacing included.
const TEXT_SPACING = `
  * { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
  p { margin-bottom: 2em !important; }
`;

const APPROVAL_ID = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";

/** The four states Task 6 names, in the shape `accessibility.spec.ts` established. */
const APPROVAL_STATES = [
  ["pending", "pending", "Approve as baseline"],
  ["presented-expired", "pending-overdue", "Dismiss expired request"],
  ["terminal", "rejected", "Terminal approval state: rejected"],
  ["post-promotion-terminal", "consumed", "promoted bbbbbbbb-2222-4222-8222-bbbbbbbbbbbb replacing baseline-v12"],
] as const;

async function routeApproval(page: Page, state: string) {
  const overdue = state === "pending-overdue";
  const approval = {
    approval_id: APPROVAL_ID,
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
    if (url.pathname.endsWith(`/${APPROVAL_ID}`)) return route.fulfill({ json: approval });
    if (url.pathname.endsWith("/approvals")) return route.fulfill({ json: { items: [approval] } });
    return route.fallback();
  });
}

async function applyDimensions(page: Page, zoom: string) {
  // Injected AFTER navigation, per `layout-accessibility.spec.ts`: `page.goto`
  // replaces the document and discards any style tag added before it, so a single
  // pre-loop `addStyleTag` applies WCAG 1.4.12 to no scanned page at all.
  await page.addStyleTag({ content: TEXT_SPACING });
  await page.evaluate((value) => { document.documentElement.style.zoom = value; }, zoom);
}

async function expectDesktopLayoutClean(page: Page) {
  await expectAxeClean(page);
  const layout = await page.evaluate(() => {
    const sticky = Array.from(document.querySelectorAll<HTMLElement>("*")).filter((node) =>
      ["sticky", "fixed"].includes(getComputedStyle(node).position) && node.textContent?.trim(),
    );
    const stickyOverlap = sticky.some((node, index) => sticky.slice(index + 1).some((other) => {
      const a = node.getBoundingClientRect(); const b = other.getBoundingClientRect();
      return a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
    }));
    // `.font-mono` is this app's identifier rendering convention (IdentifierCopyButton,
    // EvidenceTargetPanel, ChatView, RunsTable). `[data-identifier]` and
    // `[data-contained-scroll]` occur nowhere in `src/`, so the original
    // `code,[data-identifier]` pair selected an empty set on every scanned page.
    const unreadableIdentifier = Array.from(
      document.querySelectorAll<HTMLElement>("code,[data-identifier],.font-mono"),
    ).some((node) => node.scrollWidth > node.clientWidth && !node.closest("[data-contained-scroll]"));
    return {
      horizontalScroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
      stickyOverlap,
      unreadableIdentifier,
    };
  });
  expect(layout).toEqual({ horizontalScroll: false, stickyOverlap: false, unreadableIdentifier: false });
}

test("keeps the Epic 2-4 desktop journey conformant across zoom, text spacing, and reduced motion", async ({ page }) => {
  test.setTimeout(180_000);
  const journey = await installApiStubs(page);
  journey.completeRun();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });

  // Seed the draft once. `repairJourneyStubState` returns the draft activity only
  // after a message is accepted, and that state lives in the page's route handler,
  // so it persists across the navigations below.
  await page.goto(JOURNEY[0].url);
  await page.getByRole("textbox", { name: "Message" }).fill("Create a reversible repair draft.");
  await page.getByRole("button", { name: "Send" }).click();
  await expect(page.getByRole("region", { name: "Draft proposal" })).toBeVisible();

  for (const zoom of ["1", "2"] as const) {
    for (const { url, ready } of JOURNEY) {
      await page.goto(url);
      await ready(page);
      await applyDimensions(page, zoom);
      await expectDesktopLayoutClean(page);
    }
  }
});

// Task 6 names "all four approval-panel states" on Results. `accessibility.spec.ts`
// scans them full-page under both motion preferences at default zoom; this covers
// the dimension that spec does not — 200% zoom under WCAG text spacing — rather
// than duplicating those sixteen scans.
test("keeps all four approval-panel states conformant at 200 percent zoom under text spacing", async ({ page }) => {
  test.setTimeout(180_000);
  const journey = await installApiStubs(page);
  journey.completeRun();
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.emulateMedia({ reducedMotion: "reduce" });

  for (const [, state, expectedText] of APPROVAL_STATES) {
    await routeApproval(page, state);
    await page.goto(`/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`);
    await expect(page.getByText(expectedText)).toBeVisible();
    await applyDimensions(page, "2");
    await expectDesktopLayoutClean(page);
  }
});

// Browser disclosure: the deterministic stubs measure Chat's disconnected fallback.
// NOT COVERED: chat_sse_healthy_stream:needs_local_sse_server.
// Component-only matrix states include clarification/refusal, stale/rejected drafts,
// and provenance-without-evidence variants not reachable here.
