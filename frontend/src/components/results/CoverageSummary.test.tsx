/**
 * D-04/D-07/RES-01 coverage for the coverage stat row: real numbers
 * formatted via Intl.NumberFormat/one-decimal-hours, and independent
 * null-safe "Not computed" guards per card (never a misleading zero).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { CoverageSummary } from "./CoverageSummary";

describe("CoverageSummary: populated [UI-SPEC E3/populated]", () => {
  it("formats total_cost via Intl.NumberFormat USD and total_unmet_hours to one decimal", () => {
    render(
      <CoverageSummary total_cost={1234.5} total_unmet_hours={12.3} />,
    );

    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
    expect(screen.getByText("12.3 h")).toBeInTheDocument();
  });
});

describe("CoverageSummary: total_cost null [D-07, RES-01 prohibition]", () => {
  it("renders 'Not computed' for the cost card, never $0.00 or a plain 0", () => {
    render(<CoverageSummary total_cost={null} total_unmet_hours={12.3} />);

    expect(screen.getByText("Not computed")).toBeInTheDocument();
    expect(screen.queryByText("$0.00")).not.toBeInTheDocument();
    expect(screen.queryByText(/^0$/)).not.toBeInTheDocument();
  });
});

describe("CoverageSummary: partial null [UI-SPEC E3/partial]", () => {
  it("cost populated + hours null coexist, each card guarding independently", () => {
    render(<CoverageSummary total_cost={1234.5} total_unmet_hours={null} />);

    expect(screen.getByText("$1,234.50")).toBeInTheDocument();
    expect(screen.getByText("Not computed")).toBeInTheDocument();
  });
});

describe("CoverageSummary: both null [UI-SPEC E3/populated-to-null]", () => {
  it("renders 'Not computed' independently for both cards", () => {
    render(<CoverageSummary total_cost={null} total_unmet_hours={null} />);

    expect(screen.getAllByText("Not computed")).toHaveLength(2);
  });
});
