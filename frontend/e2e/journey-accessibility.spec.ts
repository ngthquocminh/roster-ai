import { expect, test, type Page } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { CONVERSATION_ID, installApiStubs, SCENARIO_ID, SCHEDULE_RUN_ID } from "./support/apiStubs";

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
    const unreadableIdentifier = Array.from(document.querySelectorAll<HTMLElement>("code,[data-identifier]"))
      .some((node) => node.scrollWidth > node.clientWidth && !node.closest("[data-contained-scroll]"));
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
  await page.addStyleTag({ content: "* { line-height: 1.5 !important; letter-spacing: 0.12em !important; word-spacing: 0.16em !important; }" });

  for (const zoom of ["1", "2"] as const) {
    for (const url of [
      `/scenarios/${SCENARIO_ID}?conversation=${CONVERSATION_ID}`,
      `/scenarios/${SCENARIO_ID}/runs`,
      `/scenarios/${SCENARIO_ID}/runs/${SCHEDULE_RUN_ID}`,
    ]) {
      await page.goto(url);
      await page.evaluate((value) => { document.documentElement.style.zoom = value; }, zoom);
      await expectDesktopLayoutClean(page);
    }
  }
});

// Browser disclosure: the deterministic stubs measure Chat's disconnected fallback.
// NOT COVERED: chat_sse_healthy_stream:needs_local_sse_server.
// Component-only matrix states include clarification/refusal, stale/rejected drafts,
// approval expired/stale, and provenance-without-evidence variants not reachable here.
