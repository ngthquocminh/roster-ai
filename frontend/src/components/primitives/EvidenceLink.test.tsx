import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { EvidenceLink, VerifiedMark } from "./EvidenceLink";

describe("EvidenceLink", () => {
  it("builds the complete evidence locator label and activates it", () => {
    const onActivate = vi.fn();
    render(
      <EvidenceLink
        fieldOrRange="13:00–17:00"
        group="Demand"
        id="evidence-origin-activity-1-0-0"
        onActivate={onActivate}
        record="DEM-204"
        version="v7"
      />,
    );

    const control = screen.getByRole("button", {
      name: "Evidence: Demand DEM-204, 13:00–17:00, fixture v7",
    });
    expect(control).toHaveAttribute("id", "evidence-origin-activity-1-0-0");
    // Unlike `verified`, the plain form shows its full label as visible text
    // and keeps its underline (there IS text here for it to decorate).
    expect(control.querySelector(".sr-only")).not.toBeInTheDocument();
    expect(control.className).toContain("underline");
    fireEvent.click(control);
    expect(onActivate).toHaveBeenCalledOnce();
  });

  it("folds the verified state into the same control's accessible name, not a separate label", () => {
    render(
      <EvidenceLink
        fieldOrRange="qualifications: pick"
        group="workers"
        id="evidence-origin-activity-2-0-0"
        onActivate={vi.fn()}
        record="w1"
        verified
        version="v7"
      />,
    );

    const control = screen.getByRole("button", {
      name: "Verified Evidence: workers w1, qualifications: pick, fixture v7",
    });
    expect(control).toBeInTheDocument();
    // The button is the check icon alone -- one clickable control, not an
    // icon beside a separate visible text link. The full label still reaches
    // a screen reader via `sr-only` text (asserted above via accessible name).
    expect(control.querySelector("svg")).toBeInTheDocument();
    expect(control.querySelector(".sr-only")).toHaveTextContent(
      "Verified Evidence: workers w1, qualifications: pick, fixture v7",
    );
    // No visible text to underline -- `underline` here previously painted a
    // stray decoration line under the bare icon. A circular hover highlight
    // stands in as the icon-button affordance instead.
    expect(control.className).not.toContain("underline");
    expect(control.className).toContain("hover:bg-muted");
  });

  it("also folds the verified state into the href-based (anchor) variant", () => {
    render(
      <EvidenceLink
        fieldOrRange="qualifications: pick"
        group="workers"
        href="/scenarios/s1/data?group=workers&record=w1"
        id="evidence-origin-activity-3-0-0"
        record="w1"
        verified
        version="v7"
      />,
    );

    const link = screen.getByRole("link", {
      name: "Verified Evidence: workers w1, qualifications: pick, fixture v7",
    });
    expect(link).toHaveAttribute("href", "/scenarios/s1/data?group=workers&record=w1");
  });
});

describe("VerifiedMark", () => {
  it("renders an accessibly-labelled check with no link", () => {
    render(<VerifiedMark />);

    expect(screen.getByRole("img", { name: "Verified" })).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });
});
