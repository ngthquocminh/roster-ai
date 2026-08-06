import { createRef } from "react";
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EvidenceHighlight } from "./EvidenceHighlight";

describe("EvidenceHighlight", () => {
  it("provides a quiet, focusable evidence wrapper and forwards its ref", () => {
    const ref = createRef<HTMLDivElement>();
    render(
      <EvidenceHighlight ref={ref}>
        Demand DEM-204
      </EvidenceHighlight>,
    );

    expect(ref.current).toHaveAttribute("tabindex", "-1");
    expect(ref.current).toHaveClass(
      "bg-evidence-surface",
      "text-evidence-foreground",
      "border-evidence-border",
      "rounded-evidence",
      "p-evidence-inset",
    );
  });
});
