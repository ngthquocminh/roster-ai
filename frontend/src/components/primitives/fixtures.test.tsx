import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PRIMITIVE_FIXTURES } from "./fixtures";

describe("primitive visual-regression fixtures", () => {
  it("enumerates every declared state for all eight primitives", () => {
    const statesByPrimitive = new Map<string, string[]>();
    for (const fixture of PRIMITIVE_FIXTURES) {
      statesByPrimitive.set(fixture.primitive, [
        ...(statesByPrimitive.get(fixture.primitive) ?? []),
        fixture.state,
      ]);
    }

    expect(statesByPrimitive.get("StatusBadge")).toEqual([
      "queued",
      "running",
      "completed",
      "infeasible",
      "timed out",
      "cancelled",
      "failed",
      "rejected",
      "expired",
      "stale",
    ]);
    expect(statesByPrimitive.get("InlineAlert")).toEqual([
      "default",
      "default with action",
      "destructive",
      "destructive with action",
    ]);
    expect(statesByPrimitive.get("Skeleton")).toEqual([
      "text line",
      "table region",
    ]);
    expect(statesByPrimitive.get("EmptyState")).toEqual([
      "without action",
      "with action",
    ]);
    expect(statesByPrimitive.get("ReconnectBanner")).toEqual([
      "disconnected",
      "reconnecting",
      "reconnected",
    ]);
    expect(statesByPrimitive.get("EvidenceLink")).toEqual([
      "record",
      "field or range",
    ]);
    expect(statesByPrimitive.get("EvidenceHighlight")).toEqual([
      "row",
      "record card",
    ]);
    expect(statesByPrimitive.get("IdentifierCopyButton")).toEqual(["idle", "copied"]);
  });

  it("renders every fixture deterministically without providers", () => {
    for (const fixture of PRIMITIVE_FIXTURES) {
      const first = render(fixture.render()).container.innerHTML;
      const second = render(fixture.render()).container.innerHTML;
      expect(second, `${fixture.primitive}: ${fixture.state}`).toBe(first);
    }
  });

  it("covers every primitive by its governed name", () => {
    expect(new Set(PRIMITIVE_FIXTURES.map(({ primitive }) => primitive))).toEqual(
      new Set([
        "StatusBadge",
        "InlineAlert",
        "Skeleton",
        "EmptyState",
        "ReconnectBanner",
        "EvidenceLink",
        "EvidenceHighlight",
        "IdentifierCopyButton",
      ]),
    );
  });

  it("uses distinct literal text for every state within a primitive", () => {
    const textByPrimitive = new Map<string, string[]>();

    for (const fixture of PRIMITIVE_FIXTURES) {
      const { container, unmount } = render(fixture.render());
      const text = container.textContent?.replace(/\s+/g, " ").trim() ?? "";
      textByPrimitive.set(fixture.primitive, [
        ...(textByPrimitive.get(fixture.primitive) ?? []),
        text,
      ]);
      unmount();
    }

    for (const [primitive, texts] of textByPrimitive) {
      expect(texts.every(Boolean), primitive).toBe(true);
      expect(new Set(texts).size, primitive).toBe(texts.length);
    }
  });

  it("keeps every fixture action at the 44px class floor", () => {
    for (const fixture of PRIMITIVE_FIXTURES) {
      const { container, unmount } = render(fixture.render());
      for (const control of Array.from(container.querySelectorAll("button, a"))) {
        expect(control, `${fixture.primitive}: ${fixture.state}`).toHaveClass(
          "min-h-11",
        );
      }
      unmount();
    }
  });

  it("keeps evidence highlights quiet and skeletons reduced-motion safe", () => {
    for (const fixture of PRIMITIVE_FIXTURES) {
      const { container, unmount } = render(fixture.render());
      if (fixture.primitive === "EvidenceHighlight") {
        const root = container.firstElementChild;
        expect(root?.className).not.toMatch(/(?:^|\s)animate-/);
        expect(root?.className).not.toMatch(/(?:^|\s)shadow-/);
      }
      if (fixture.primitive === "Skeleton") {
        for (const skeleton of Array.from(
          container.querySelectorAll('[data-slot="skeleton"]'),
        )) {
          expect(skeleton).toHaveClass("motion-reduce:animate-none");
        }
      }
      unmount();
    }
  });
});
