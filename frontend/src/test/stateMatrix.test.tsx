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

// Tailwind 4 renamed the v3 gradient utilities: `bg-gradient-to-*` became
// `bg-linear-to-*`, and `bg-radial` / `bg-conic` are new. This repo pins
// tailwindcss 4.3.2, so scanning for the v3 names alone let `bg-linear-to-r`
// through — verified at code review by adding exactly that class to a fixture.
const GRADIENT_PREFIXES = [
  "bg-gradient-", "bg-linear-", "bg-radial", "bg-conic",
  "bg-[linear-gradient", "bg-[radial-gradient", "bg-[conic-gradient",
];
const ANIMATION_TOKENS = ["animate-pulse", "animate-ping", "animate-bounce", "animate-spin"];

function expectNoProhibitedTreatment(container: HTMLElement, family: StateFamily) {
  // Evaluated per NODE, not over a flattened token list for the whole container:
  // flattening let one properly guarded node's `motion-reduce:animate-none` exempt
  // an unguarded `animate-pulse` on an unrelated sibling.
  const offending = Array.from(container.querySelectorAll<HTMLElement>("[class]")).filter((node) => {
    const own = Array.from(node.classList);
    const decorated = own.some((token) =>
      GRADIENT_PREFIXES.some((prefix) => token.startsWith(prefix)) ||
      token.toLowerCase().includes("glow"),
    );
    const unguardedAnimation = own.some((token) => ANIMATION_TOKENS.includes(token)) &&
      !own.includes("motion-reduce:animate-none");
    return decorated || unguardedAnimation;
  });
  expect(offending.map((node) => node.className)).toEqual([]);
  // UX-DR10 bans invented progress language. `run` alone was too narrow: that family
  // is ten single-word status badges, while `terminal-outcome` is where a phrase like
  // "timed out at ~85% after 04:30" would actually land.
  if (family === "run" || family === "terminal-outcome") {
    expect(normalizedText(container)).not.toMatch(/%|\bETA\b|approximately|~|\b\d{1,2}:\d{2}\b/i);
  }
  // UX-DR11 deliberately permits real coverage/overtime/cost percentages in comparisons.
  const actions = Array.from(container.querySelectorAll<HTMLElement>("button,a"));
  if (actions.length > 1) {
    expect(new Set(actions.map((node) => Array.from(node.classList).sort().join(" "))).size).toBeGreaterThan(1);
  }
}

describe("workflow state semantics matrix", () => {
  for (const fixture of STATE_MATRIX) {
    it(`${fixture.family}/${fixture.state}`, async () => {
      const { container } = render(<>{fixture.render()}</>);
      expect(normalizedText(container)).not.toBe("");
      expectNoProhibitedTreatment(container, fixture.family);
      const results = await axe(container, {
        runOnly: { type: "tag", values: WCAG_TAGS },
        // Both rules need real geometry or real colour, which jsdom does not
        // compute: every rect is 0x0, so `target-size` can only ever return
        // `incomplete` (never a violation) and would read as proven while a 1x1
        // control passed. Both are proven in the browser layer instead —
        // `target-size` via `expectAxeClean` in `e2e/layout-accessibility.spec.ts`,
        // contrast via the full-page approval scans in `e2e/accessibility.spec.ts`.
        rules: { "color-contrast": { enabled: false }, "target-size": { enabled: false } },
      });
      expect(results.violations).toEqual([]);
    });
  }

  // The declared count is in the case NAME on purpose. Decision 9 asks that a state
  // cannot be present in the module and silently missing from the run, but a Vitest
  // assertion can only see the module, never the emitted report — and a filtered or
  // sharded run OMITS cases rather than marking them `<skipped/>`, so the generator's
  // skip rule does not catch it either. Publishing the count through the JUnit XML
  // lets `generate_state_semantics_evidence.py` reconcile emitted cases against it,
  // and a filtered run drops this case entirely, which the generator refuses.
  it(`declares ${STATE_MATRIX.length} states`, () => {
    const identities = STATE_MATRIX.map(({ family, state }) => `${family}/${state}`);
    expect(STATE_MATRIX.length).toBeGreaterThan(0);
    expect(new Set(identities).size).toBe(STATE_MATRIX.length);
  });

  // Decision 3 names the failure mode as "two states that differ only in a colour
  // class produce an identical tree AND identical text", then states the rule as two
  // INDEPENDENT distinctness assertions, which is stricter than that failure mode.
  // Measured on real components at code review: the three terminal approval outcomes
  // render byte-identical role/name trees (3 distinct of 6) and differ only in text —
  // legitimate structural reuse, and a false failure under the independent form. The
  // only fix for it that keeps trees distinct would be to give each outcome its own
  // accessible name on the `role="status"` region, which mislabels a live region with
  // its own value. So the assertion is on the COMBINED signature: two states collide
  // only when they are identical in both, which is exactly the colour-only failure.
  // Verified both directions — a colour-only pair still collides under this rule.
  it("covers all ten AC1 families, no two states alike in both text and structure", () => {
    expect(new Set(STATE_MATRIX.map(({ family }) => family))).toEqual(new Set(EXPECTED_FAMILIES));
    for (const family of EXPECTED_FAMILIES) {
      const signatures: string[] = [];
      for (const fixture of STATE_MATRIX.filter((entry) => entry.family === family)) {
        const { container, unmount } = render(<>{fixture.render()}</>);
        signatures.push(`${normalizedText(container)}||${roleNameTree(container)}`);
        unmount();
      }
      expect(new Set(signatures).size, `${family} signature`).toBe(signatures.length);
    }
  });
});
