/**
 * RUN-03 coverage (UI-SPEC E3) for the honest in-flight wait panel: the
 * PENDING/RUNNING copy, the null/terminal-status "render nothing" cases, and
 * the negative guarantee (no cancel affordance, no determinate-progress
 * element — see threat T-3-08).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { RunInFlightPanel } from "./RunInFlightPanel";

function runOut(overrides: Record<string, unknown> = {}) {
  return {
    id: "run-1",
    scenario_id: "scenario-1",
    status: "PENDING",
    created_at: "2026-07-18T09:00:00Z",
    started_at: null,
    finished_at: null,
    solver_status: null,
    error: null,
    ...overrides,
  };
}

describe("RunInFlightPanel: null run [UI-SPEC E3/empty-hidden]", () => {
  it("renders nothing — not even empty chrome", () => {
    const { container } = render(<RunInFlightPanel run={null} />);

    expect(container).toBeEmptyDOMElement();
  });
});

describe("RunInFlightPanel: PENDING [UI-SPEC E3/populated-PENDING]", () => {
  it("renders the 'Queued' title and the next-in-line body", () => {
    render(<RunInFlightPanel run={runOut({ status: "PENDING" })} />);

    expect(screen.getByText("Queued")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Waiting for the solver to pick this up — it's next in line.",
      ),
    ).toBeInTheDocument();
  });
});

describe("RunInFlightPanel: RUNNING [UI-SPEC E3/populated-RUNNING]", () => {
  it("renders the 'Solving…' title and the honest multi-minute / no-cancel body", () => {
    render(<RunInFlightPanel run={runOut({ status: "RUNNING" })} />);

    expect(screen.getByText("Solving…")).toBeInTheDocument();
    const body = screen.getByText(/This can take a few minutes/);
    expect(body.textContent).toContain(
      "It can't be cancelled once started — let it finish.",
    );
  });
});

describe("RunInFlightPanel: terminal status [defensive]", () => {
  it("renders nothing for a COMPLETED run", () => {
    const { container } = render(
      <RunInFlightPanel run={runOut({ status: "COMPLETED" })} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("renders nothing for a FAILED run", () => {
    const { container } = render(
      <RunInFlightPanel run={runOut({ status: "FAILED" })} />,
    );

    expect(container).toBeEmptyDOMElement();
  });
});

describe("RunInFlightPanel: honesty [T-3-08, RUN-03 prohibitions]", () => {
  it("renders no cancel control and no progressbar in PENDING or RUNNING state", () => {
    for (const status of ["PENDING", "RUNNING"]) {
      const { unmount } = render(<RunInFlightPanel run={runOut({ status })} />);
      expect(
        screen.queryByRole("button", { name: /cancel/i }),
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
      unmount();
    }
  });
});
