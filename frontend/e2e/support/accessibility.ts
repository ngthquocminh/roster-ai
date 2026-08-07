import AxeBuilder from "@axe-core/playwright";
import { expect, type Page } from "@playwright/test";

export const WCAG_TAGS = [
  "wcag2a",
  "wcag2aa",
  "wcag21a",
  "wcag21aa",
  "wcag22aa",
] as const;

export async function expectAxeClean(page: Page, include?: string) {
  let builder = new AxeBuilder({ page })
    .withTags([...WCAG_TAGS])
    .options({
      runOnly: { type: "tag", values: [...WCAG_TAGS] },
      rules: { "target-size": { enabled: true } },
    });

  if (include) builder = builder.include(include);

  const results = await builder.analyze();

  expect(results.violations, JSON.stringify(results.violations, null, 2)).toEqual([]);
}
