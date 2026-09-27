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

    expect(
      screen.getByRole("button", {
        name: "Verified Evidence: workers w1, qualifications: pick, fixture v7",
      }),
    ).toBeInTheDocument();
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
