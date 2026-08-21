import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { RunStatusBadge } from "./RunStatusBadge";

const STATUSES = [
  "solver_queued",
  "solver_running",
  "cancellation_requested",
  "solver_completed",
  "solver_infeasible",
  "solver_timed_out",
  "solver_cancelled",
  "solver_failed",
] as const;

const FORBIDDEN = [/%/, /eta/i, /remaining/i, /likely/i, /probably/i, /optimizing/i, /almost done/i];

describe("RunStatusBadge", () => {
  it.each(STATUSES)("renders literal text for %s with no forbidden token", (status) => {
    const { container } = render(<RunStatusBadge status={status} />);
    const text = container.textContent ?? "";
    expect(text.length).toBeGreaterThan(0);
    for (const pattern of FORBIDDEN) expect(text).not.toMatch(pattern);
  });

  it("renders a distinct, literal label for all five terminal states (AC3)", () => {
    const terminal = [
      "solver_completed",
      "solver_infeasible",
      "solver_timed_out",
      "solver_cancelled",
      "solver_failed",
    ] as const;
    const labels = terminal.map((status) => {
      const { container, unmount } = render(<RunStatusBadge status={status} />);
      const label = container.textContent;
      unmount();
      return label;
    });
    expect(new Set(labels).size).toBe(terminal.length);
  });

  it("carries the literal text in aria-label, not just visually", () => {
    render(<RunStatusBadge status="solver_infeasible" />);
    expect(screen.getByLabelText("Infeasible")).toBeInTheDocument();
  });

  it("distinguishes non-terminal cancellation_requested from queued and running", () => {
    const queued = render(<RunStatusBadge status="solver_queued" />).container.textContent;
    const running = render(<RunStatusBadge status="solver_running" />).container.textContent;
    const requested = render(<RunStatusBadge status="cancellation_requested" />).container.textContent;
    expect(new Set([queued, running, requested]).size).toBe(3);
  });
});
