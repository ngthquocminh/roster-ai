/**
 * RUN-04's icon+text status convention (UI-SPEC Color section mapping) —
 * asserts each of the four statuses' visible label, the RUNNING variant's
 * spinning icon, and an honest fallback for an unrecognized status string.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { RunStatusLabel } from "./RunStatusLabel";

describe("RunStatusLabel: status labels", () => {
  it('renders "Queued" for PENDING', () => {
    render(<RunStatusLabel status="PENDING" />);
    expect(screen.getByText("Queued")).toBeInTheDocument();
  });

  it('renders "Running" for RUNNING with a spinning icon', () => {
    const { container } = render(<RunStatusLabel status="RUNNING" />);
    expect(screen.getByText("Running")).toBeInTheDocument();
    const icon = container.querySelector("svg");
    expect(icon?.getAttribute("class")).toMatch(/animate-spin/);
  });

  it('renders "Completed" for COMPLETED, neutral (not destructive)', () => {
    const { container } = render(<RunStatusLabel status="COMPLETED" />);
    const label = screen.getByText("Completed");
    expect(label).toBeInTheDocument();
    expect(label.className).not.toMatch(/destructive/);
    expect(container.querySelector("svg")?.getAttribute("class")).not.toMatch(
      /animate-spin/,
    );
  });

  it('renders "Failed" for FAILED, destructive', () => {
    render(<RunStatusLabel status="FAILED" />);
    const label = screen.getByText("Failed");
    expect(label.className).toMatch(/destructive/);
  });

  it("renders the raw status string as the label for an unknown status", () => {
    render(<RunStatusLabel status="WEIRD" />);
    expect(screen.getByText("WEIRD")).toBeInTheDocument();
  });
});
