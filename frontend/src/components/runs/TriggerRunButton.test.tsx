/**
 * RUN-01 coverage (UI-SPEC E1) for the "Run Scenario" trigger CTA's every
 * idle/loading/submitting/in-progress/error state, plus RUN-03's negative
 * guarantee (no cancel affordance, no determinate-progress element) — see
 * threat T-3-08. Purely presentational: no hook mocking needed, every state
 * is driven directly via props.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { TriggerRunButton } from "./TriggerRunButton";

function baseProps() {
  return {
    onTrigger: vi.fn(),
    isLoadingList: false,
    runInProgress: false,
    isPending: false,
    error: null as unknown,
  };
}

describe("TriggerRunButton: idle [UI-SPEC E1/empty]", () => {
  it("renders an enabled button labeled 'Run Scenario'", () => {
    render(<TriggerRunButton {...baseProps()} />);

    const button = screen.getByRole("button", { name: "Run Scenario" });
    expect(button).toBeEnabled();
  });
});

describe("TriggerRunButton: initial list loading [UI-SPEC E1/loading-initial]", () => {
  it("disables the button with no caption while the initial list fetch is in flight", () => {
    render(<TriggerRunButton {...baseProps()} isLoadingList={true} />);

    expect(screen.getByRole("button", { name: "Run Scenario" })).toBeDisabled();
    expect(
      screen.queryByText("A run is already in progress for this scenario."),
    ).not.toBeInTheDocument();
  });
});

describe("TriggerRunButton: submitting [UI-SPEC E1/loading-submit]", () => {
  it("disables the button and shows a spinner + 'Starting…'", () => {
    render(<TriggerRunButton {...baseProps()} isPending={true} />);

    const button = screen.getByRole("button", { name: "Starting…" });
    expect(button).toBeDisabled();
    expect(button.querySelector("svg")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Run Scenario" }),
    ).not.toBeInTheDocument();
  });
});

describe("TriggerRunButton: in progress [UI-SPEC E1/disabled-in-progress]", () => {
  it("disables the button and renders the in-progress caption", () => {
    render(<TriggerRunButton {...baseProps()} runInProgress={true} />);

    expect(screen.getByRole("button", { name: "Run Scenario" })).toBeDisabled();
    expect(
      screen.getByText("A run is already in progress for this scenario."),
    ).toBeInTheDocument();
  });
});

describe("TriggerRunButton: error 404 [UI-SPEC E1/error-404]", () => {
  it("renders 'This scenario no longer exists.' when error.status is 404", () => {
    render(<TriggerRunButton {...baseProps()} error={{ status: 404 }} />);

    expect(
      screen.getByText("This scenario no longer exists."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Couldn't start the run. Try again."),
    ).not.toBeInTheDocument();
  });
});

describe("TriggerRunButton: error other [UI-SPEC E1/error-other]", () => {
  it("renders \"Couldn't start the run. Try again.\" for a non-404 error object", () => {
    render(<TriggerRunButton {...baseProps()} error={{ status: 500 }} />);

    expect(
      screen.getByText("Couldn't start the run. Try again."),
    ).toBeInTheDocument();
  });

  it("renders \"Couldn't start the run. Try again.\" for a thrown network error with no status field", () => {
    render(<TriggerRunButton {...baseProps()} error={new Error("network error")} />);

    expect(
      screen.getByText("Couldn't start the run. Try again."),
    ).toBeInTheDocument();
  });
});

describe("TriggerRunButton: click [RUN-01]", () => {
  it("calls onTrigger exactly once when the enabled button is clicked", async () => {
    const user = userEvent.setup();
    const props = baseProps();
    render(<TriggerRunButton {...props} />);

    await user.click(screen.getByRole("button", { name: "Run Scenario" }));

    expect(props.onTrigger).toHaveBeenCalledTimes(1);
  });
});

describe("TriggerRunButton: honesty [T-3-08, RUN-03 prohibitions]", () => {
  it("never renders a cancel control or a progressbar in any state", () => {
    const states = [
      baseProps(),
      { ...baseProps(), isLoadingList: true },
      { ...baseProps(), isPending: true },
      { ...baseProps(), runInProgress: true },
      { ...baseProps(), error: { status: 404 } },
      { ...baseProps(), error: { status: 500 } },
    ];

    for (const props of states) {
      const { unmount } = render(<TriggerRunButton {...props} />);
      expect(
        screen.queryByRole("button", { name: /cancel/i }),
      ).not.toBeInTheDocument();
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
      unmount();
    }
  });
});
