import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { expect, test } from "@playwright/test";

import { installApiStubs, SCENARIO_ID } from "./support/apiStubs";

// e2e/ is a separate TS project (tsconfig.e2e.json) from src/ (tsconfig.app.json) under project
// references, so it can't `import` across that boundary. Read the real component source instead
// of hand-copying its class list, so this still breaks loudly — instead of silently drifting — the
// moment EvidenceHighlight.tsx's classes change.
function readEvidenceHighlightClass(): string {
  const sourcePath = fileURLToPath(
    new URL("../src/components/primitives/EvidenceHighlight.tsx", import.meta.url),
  );
  const source = readFileSync(sourcePath, "utf8");
  const match = /EVIDENCE_HIGHLIGHT_CLASS\s*=\s*\n?\s*"([^"]+)"/.exec(source);
  if (!match) throw new Error("Could not locate EVIDENCE_HIGHLIGHT_CLASS in EvidenceHighlight.tsx");
  return match[1];
}

const demandUrl = `/scenarios/${SCENARIO_ID}/data?group=demand`;

test.beforeEach(async ({ page }) => {
  await installApiStubs(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
});

test("globally neutralizes non-essential animation without removing status text", async ({ page }) => {
  await page.route("**/projection/demand?**", async (route) => {
    await new Promise((resolve) => setTimeout(resolve, 250));
    await route.fallback();
  });
  await page.goto(demandUrl);

  await expect(page.getByRole("status", { name: "Loading scenario data" })).toHaveAccessibleName("Loading scenario data");
  const tableStatus = page.getByRole("status").filter({ hasText: "Showing" });
  await expect(tableStatus).not.toBeEmpty();

  const reducedStyle = await page.getByRole("button", { name: "Choose columns" }).evaluate((element) => {
    const style = getComputedStyle(element);
    return {
      animationDuration: style.animationDuration,
      animationIterationCount: style.animationIterationCount,
      transitionDuration: style.transitionDuration,
      scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
    };
  });
  expect(Number.parseFloat(reducedStyle.animationDuration)).toBeLessThanOrEqual(0.00001);
  expect(reducedStyle.animationIterationCount).toBe("1");
  expect(reducedStyle.scrollBehavior).toBe("auto");
  expect(Number.parseFloat(reducedStyle.transitionDuration)).toBeLessThanOrEqual(0.00001);
});

test("retains the stale workspace status under reduced motion", async ({ page }) => {
  let contextRequests = 0;
  await page.route(`**/api/v1/scenarios/${SCENARIO_ID}`, async (route) => {
    contextRequests += 1;
    if (contextRequests === 1) return route.fallback();
    return route.fulfill({
      body: JSON.stringify({ detail: "simulated stale refresh" }),
      contentType: "application/json",
      status: 503,
    });
  });
  await page.goto(demandUrl);
  await expect(page.getByRole("heading", { level: 1, name: "sample_tiny_input" })).toBeVisible();
  await page.getByRole("link", { name: "Change scenario" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Fixture catalogue" })).toBeVisible();
  await page.goBack();
  await expect.poll(() => contextRequests).toBeGreaterThan(1);
  await expect(page.getByRole("status").filter({ hasText: "Stale — last verified at" })).not.toBeEmpty();
});

test("keeps evidence highlighting visually identical across motion preferences", async ({ page }) => {
  // EvidenceHighlight (frontend/src/components/primitives/EvidenceHighlight.tsx) isn't wired into
  // a live route yet — it currently only ships through the Story 1.6 primitives fixture registry.
  // Layer A (jsdom) can't compute real animation/paint values (Task 1's color-contrast note applies
  // equally here), so this still injects a node rather than navigating to a real usage. What makes
  // it a proof of the *shipped* component, not a stand-in: the class list is read from the real
  // component source (see readEvidenceHighlightClass above) instead of hand-copied, so this breaks
  // loudly — instead of silently drifting — the moment the component's classes change.
  const evidenceHighlightClass = readEvidenceHighlightClass();
  await page.goto("/");
  const styles = [];
  for (const reducedMotion of ["no-preference", "reduce"] as const) {
    await page.emulateMedia({ reducedMotion });
    styles.push(await page.evaluate((className) => {
      const node = document.createElement("div");
      node.className = className;
      node.textContent = "Evidence target";
      document.body.append(node);
      const style = getComputedStyle(node);
      const snapshot = {
        animationName: style.animationName,
        backgroundColor: style.backgroundColor,
        borderColor: style.borderColor,
        borderRadius: style.borderRadius,
        color: style.color,
        padding: style.padding,
      };
      node.remove();
      return snapshot;
    }, evidenceHighlightClass));
  }
  expect(styles[0]).toEqual(styles[1]);
  expect(styles[0].animationName).toBe("none");
});
