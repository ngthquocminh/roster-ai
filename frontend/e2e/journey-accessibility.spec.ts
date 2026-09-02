import { expect, test, type Page } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { CONVERSATION_ID, installApiStubs, SCENARIO_ID, SCHEDULE_RUN_ID } from "./support/apiStubs";

// Each route is paired with the heading that proves it finished rendering. Without
// this anchor `page.goto` resolves on `load`, before the stubbed queries settle, and
// every scan below measures a 64-character app shell: the code review measured
// `bodyChars: 64` / `focusable: 2` immediately after `goto` against 665 (Chat),
// 1226 (Runs) and 1837 (Results) once settled.
const JOURNEY = [
  { url: `/scenarios/${SCENARIO_ID}?conversation=${CONVERSATION_ID}`, heading: "Chat" },
  { url: `/scenarios/${SCENARIO_ID}/runs`, heading: "Runs" },
  { url: `/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`, heading: "Results" },
] as const;

// `layout-accessibility.spec.ts:102-108`'s rule verbatim, paragraph spacing included.
const TEXT_SPACING = `
  * { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }
  p { margin-bottom: 2em !important; }
`;

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

  for (const zoom of ["1", "2"] as const) {
    for (const { url, heading } of JOURNEY) {
      await page.goto(url);
      await expect(page.getByRole("heading", { name: heading })).toBeVisible();
      // Injected AFTER navigation, per the precedent: `page.goto` replaces the
      // document and discards any style tag added before it, so a single
      // pre-loop `addStyleTag` applies WCAG 1.4.12 to no scanned page at all.
      await page.addStyleTag({ content: TEXT_SPACING });
      await page.evaluate((value) => { document.documentElement.style.zoom = value; }, zoom);
      await expectDesktopLayoutClean(page);
    }
  }
});

// Browser disclosure: the deterministic stubs measure Chat's disconnected fallback.
// NOT COVERED: chat_sse_healthy_stream:needs_local_sse_server.
// Component-only matrix states include clarification/refusal, stale/rejected drafts,
// approval expired/stale, and provenance-without-evidence variants not reachable here.
