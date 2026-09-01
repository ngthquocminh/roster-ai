import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import { STATE_MATRIX, type StateFamily } from "./stateMatrix";

const WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"];
const EXPECTED_FAMILIES: readonly StateFamily[] = [
  "message", "draft", "run", "comparison", "approval", "terminal-outcome",
  "alert", "skeleton", "empty-state", "provenance",
];

function normalizedText(container: HTMLElement) {
  return container.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

function roleNameTree(container: HTMLElement) {
  const selectors = "button,a,input,select,textarea,[role],[aria-label],h1,h2,h3,h4,h5,h6,ol,ul";
  return Array.from(container.querySelectorAll<HTMLElement>(selectors)).map((node) => {
    const implicit = node.tagName.toLowerCase();
    const role = node.getAttribute("role") ?? implicit;
    const name = node.getAttribute("aria-label") ?? normalizedText(node);
    return `${role}:${name}`;
  }).join("|");
}

function expectNoProhibitedTreatment(container: HTMLElement, family: StateFamily) {
  const tokens = Array.from(container.querySelectorAll<HTMLElement>("[class]"))
    .flatMap((node) => Array.from(node.classList));
  expect(tokens.some((token) =>
    token.startsWith("bg-gradient-") || token.startsWith("bg-[linear-gradient") ||
    (["animate-pulse", "animate-ping", "animate-bounce", "animate-spin"].includes(token) &&
      !tokens.includes("motion-reduce:animate-none")) ||
    token.toLowerCase().includes("glow"),
  )).toBe(false);
  if (family === "run") {
    expect(normalizedText(container)).not.toMatch(/%|\bETA\b|approximately|~|\b\d{1,2}:\d{2}\b/i);
  }
  // UX-DR11 deliberately permits real coverage/overtime/cost percentages in comparisons.
  const actions = Array.from(container.querySelectorAll<HTMLElement>("button,a"));
  if (actions.length > 1) {
    expect(new Set(actions.map((node) => Array.from(node.classList).sort().join(" "))).size).toBeGreaterThan(1);
  }
}

describe("workflow state semantics matrix", () => {
  expect(STATE_MATRIX.length).toBeGreaterThan(0);

  for (const fixture of STATE_MATRIX) {
    it(`${fixture.family}/${fixture.state}`, async () => {
      const { container } = render(<>{fixture.render()}</>);
      expect(normalizedText(container)).not.toBe("");
      expectNoProhibitedTreatment(container, fixture.family);
      const results = await axe(container, {
        runOnly: { type: "tag", values: WCAG_TAGS },
        rules: { "color-contrast": { enabled: false }, "target-size": { enabled: true } },
      });
      expect(results.violations).toEqual([]);
    });
  }

  it("emits exactly one per-state case for every matrix entry", () => {
    const identities = STATE_MATRIX.map(({ family, state }) => `${family}/${state}`);
    expect(new Set(identities).size).toBe(STATE_MATRIX.length);
  });

  it("covers all ten AC1 families with pairwise-distinct text and role/name trees", () => {
    expect(new Set(STATE_MATRIX.map(({ family }) => family))).toEqual(new Set(EXPECTED_FAMILIES));
    for (const family of EXPECTED_FAMILIES) {
      const texts: string[] = [];
      const trees: string[] = [];
      for (const fixture of STATE_MATRIX.filter((entry) => entry.family === family)) {
        const { container, unmount } = render(<>{fixture.render()}</>);
        texts.push(normalizedText(container));
        trees.push(roleNameTree(container));
        unmount();
      }
      expect(new Set(texts).size, `${family} text`).toBe(texts.length);
      expect(new Set(trees).size, `${family} tree`).toBe(trees.length);
    }
  });
});
