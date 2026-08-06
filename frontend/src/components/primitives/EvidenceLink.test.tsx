import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EvidenceLink } from "./EvidenceLink";

describe("EvidenceLink", () => {
  it("builds the complete evidence locator label and activates it", () => {
    const onActivate = vi.fn();
    render(
      <EvidenceLink
        fieldOrRange="13:00–17:00"
        group="Demand"
        onActivate={onActivate}
        record="DEM-204"
        version="v7"
      />,
    );

    const control = screen.getByRole("button", {
      name: "Evidence: Demand DEM-204, 13:00–17:00, fixture v7",
    });
    fireEvent.click(control);
    expect(onActivate).toHaveBeenCalledOnce();
  });
});
