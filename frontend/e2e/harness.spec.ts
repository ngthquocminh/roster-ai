import { expect, test } from "@playwright/test";

import { expectAxeClean } from "./support/accessibility";
import { installApiStubs } from "./support/apiStubs";

test("serves the catalogue through deterministic API stubs", async ({ page }) => {
  await installApiStubs(page);
  await page.goto("/");

  await expect(page.getByRole("heading", { level: 1, name: "Fixture catalogue" })).toBeFocused();
  await expectAxeClean(page);
});
