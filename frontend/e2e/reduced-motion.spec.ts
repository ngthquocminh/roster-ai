import { expect, test } from "@playwright/test";

import { installApiStubs, SCENARIO_ID } from "./support/apiStubs";

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
  await page.goto("/");
  const styles = [];
  for (const reducedMotion of ["no-preference", "reduce"] as const) {
    await page.emulateMedia({ reducedMotion });
    styles.push(await page.evaluate(() => {
      const node = document.createElement("div");
      node.className = "rounded-evidence border border-evidence-border bg-evidence-surface p-evidence-inset text-evidence-foreground";
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
    }));
  }
  expect(styles[0]).toEqual(styles[1]);
  expect(styles[0].animationName).toBe("none");
});
