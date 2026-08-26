/// <reference types="node" />

import { readFileSync } from "node:fs";

import { describe, expect, it } from "vitest";

const stylesheet = readFileSync("src/index.css", "utf8");

function extractBlock(selector: string) {
  const start = stylesheet.indexOf(`${selector} {`);
  if (start === -1) {
    throw new Error(`Missing ${selector} block`);
  }

  const end = stylesheet.indexOf("\n}", start);
  if (end === -1) {
    throw new Error(`Unterminated ${selector} block`);
  }

  return stylesheet.slice(start, end + 2);
}

function readHexToken(name: string) {
  const match = extractBlock(":root").match(
    new RegExp(`--${name}:\\s*(#[0-9A-Fa-f]{6});`),
  );
  if (!match) {
    throw new Error(`Missing hex token --${name}`);
  }
  return match[1];
}

function relativeLuminance(hex: string) {
  const channels = [1, 3, 5].map((offset) =>
    Number.parseInt(hex.slice(offset, offset + 2), 16) / 255,
  );
  const [red, green, blue] = channels.map((channel) =>
    channel <= 0.04045
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4,
  );
  return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
}

function contrastRatio(first: string, second: string) {
  const lighter = Math.max(relativeLuminance(first), relativeLuminance(second));
  const darker = Math.min(relativeLuminance(first), relativeLuminance(second));
  return (lighter + 0.05) / (darker + 0.05);
}

describe("ShiftMind design tokens", () => {
  it("declares the governed raw color values", () => {
    expect(extractBlock(":root")).toContain("--primary: #4F46E5;");
    expect(extractBlock(":root")).toContain("--primary-foreground: #FFFFFF;");
    expect(extractBlock(":root")).toContain("--ring: #4F46E5;");
    expect(extractBlock(":root")).toContain("--evidence-link: #4338CA;");
    expect(extractBlock(":root")).toContain("--evidence-surface: #EEF2FF;");
    expect(extractBlock(":root")).toContain("--evidence-border: #C7D2FE;");
    expect(extractBlock(":root")).toContain("--evidence-foreground: #1E1B4B;");
    expect(extractBlock(":root")).toContain("--destructive-foreground: #FFFFFF;");
  });

  it("pairs the destructive surface with a governed foreground token", () => {
    // Story 3.12 review: the solid destructive button shipped with a raw
    // `text-white` utility and no token, so nothing tied the foreground to the
    // palette and no test would notice if `--destructive` were re-themed.
    expect(extractBlock("@theme inline")).toContain(
      "--color-destructive-foreground: var(--destructive-foreground);",
    );
    expect(readHexToken("destructive-foreground")).toBe("#FFFFFF");
  });

  it("maps every ShiftMind token through Tailwind's theme namespaces", () => {
    const theme = extractBlock("@theme inline");
    const expectedDeclarations = [
      "--color-evidence-link: var(--evidence-link);",
      "--color-evidence-surface: var(--evidence-surface);",
      "--color-evidence-border: var(--evidence-border);",
      "--color-evidence-foreground: var(--evidence-foreground);",
      "--radius-evidence: 6px;",
      "--radius-data-region: 6px;",
      "--spacing-evidence-inset: 12px;",
      "--spacing-data-cell-x: 8px;",
      "--spacing-workspace-gutter: 24px;",
      "--text-page-title: 20px;",
      "--text-page-title--line-height: 1.2;",
      "--text-page-title--font-weight: 600;",
      "--text-metric: 28px;",
      "--text-metric--line-height: 1.2;",
      "--text-metric--font-weight: 600;",
      "--text-identifier: 12px;",
      "--text-identifier--line-height: 1.5;",
      "--text-identifier--font-weight: 400;",
      "--font-mono: ui-monospace, SFMono-Regular, Consolas, monospace;",
    ];

    for (const declaration of expectedDeclarations) {
      expect(theme).toContain(declaration);
    }
  });

  it("preserves the inherited radius and dark theme verbatim", () => {
    expect(extractBlock(":root")).toContain("--radius: 0.625rem;");
    expect(extractBlock(".dark")).toMatchInlineSnapshot(`
      ".dark {
          --background: oklch(0.145 0 0);
          --foreground: oklch(0.985 0 0);
          --card: oklch(0.205 0 0);
          --card-foreground: oklch(0.985 0 0);
          --popover: oklch(0.205 0 0);
          --popover-foreground: oklch(0.985 0 0);
          --primary: oklch(0.922 0 0);
          --primary-foreground: oklch(0.205 0 0);
          --secondary: oklch(0.269 0 0);
          --secondary-foreground: oklch(0.985 0 0);
          --muted: oklch(0.269 0 0);
          --muted-foreground: oklch(0.708 0 0);
          --accent: oklch(0.269 0 0);
          --accent-foreground: oklch(0.985 0 0);
          --destructive: oklch(0.704 0.191 22.216);
          --border: oklch(1 0 0 / 10%);
          --input: oklch(1 0 0 / 15%);
          --ring: oklch(0.556 0 0);
          --chart-1: oklch(0.87 0 0);
          --chart-2: oklch(0.556 0 0);
          --chart-3: oklch(0.439 0 0);
          --chart-4: oklch(0.371 0 0);
          --chart-5: oklch(0.269 0 0);
          --sidebar: oklch(0.205 0 0);
          --sidebar-foreground: oklch(0.985 0 0);
          --sidebar-primary: oklch(0.488 0.243 264.376);
          --sidebar-primary-foreground: oklch(0.985 0 0);
          --sidebar-accent: oklch(0.269 0 0);
          --sidebar-accent-foreground: oklch(0.985 0 0);
          --sidebar-border: oklch(1 0 0 / 10%);
          --sidebar-ring: oklch(0.556 0 0);
      }"
    `);
  });

  it("keeps every shipped ShiftMind foreground pair above WCAG AA", () => {
    expect(
      contrastRatio(
        readHexToken("evidence-foreground"),
        readHexToken("evidence-surface"),
      ),
    ).toBeGreaterThanOrEqual(4.5);
    expect(contrastRatio(readHexToken("evidence-link"), "#FFFFFF")).toBeGreaterThanOrEqual(
      4.5,
    );
    expect(
      contrastRatio(readHexToken("primary-foreground"), readHexToken("primary")),
    ).toBeGreaterThanOrEqual(4.5);
  });
});
