import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { ErrorBanner } from "./ErrorBanner";

/**
 * SHELL-04 coverage for the backend-unreachable banner (T-1-02, ASVS V7).
 * Every test passes a *different* error shape and asserts the SAME fixed
 * copy renders — proving the banner truly ignores its input rather than
 * happening to work for one shape.
 */
describe("ErrorBanner", () => {
  it("renders the exact UI-SPEC backend-unreachable copy, including the remediation command", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBanner error={new Error("network error")} />);

    expect(
      screen.getByText("Can't reach the ShiftMind API."),
    ).toBeInTheDocument();
    expect(
      screen.getByText("uv run uvicorn api.main:app --reload"),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("renders the fixed copy when the error has an empty message [edge: SHELL-04/empty]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBanner error={new Error("")} />);

    expect(
      screen.getByText("Can't reach the ShiftMind API."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("renders the fixed copy when the error message is null/undefined [edge: SHELL-04/empty]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBanner error={{ message: null }} />);
    expect(
      screen.getByText("Can't reach the ShiftMind API."),
    ).toBeInTheDocument();

    render(<ErrorBanner error={undefined} />);
    expect(
      screen.getAllByText("Can't reach the ShiftMind API.").length,
    ).toBeGreaterThan(0);

    vi.restoreAllMocks();
  });

  it("renders none of a leaked stack trace or file path when the error message contains backend internals [T-1-02]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const leakedStack =
      "Traceback (most recent call last):\n" +
      '  File "/srv/app/services/run_service.py", line 90, in _execute\n' +
      "RuntimeError: solver crashed unexpectedly";
    render(<ErrorBanner error={new Error(leakedStack)} />);

    expect(screen.queryByText(/Traceback/)).not.toBeInTheDocument();
    expect(screen.queryByText(/run_service\.py/)).not.toBeInTheDocument();
    expect(
      screen.queryByText(/solver crashed unexpectedly/),
    ).not.toBeInTheDocument();
    expect(
      screen.getByText("Can't reach the ShiftMind API."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("renders the remediation command as a literal, unwrapped text node [edge: SHELL-04/encoding]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(<ErrorBanner error={new Error("boom")} />);

    expect(container.textContent).toContain(
      "uv run uvicorn api.main:app --reload",
    );

    vi.restoreAllMocks();
  });
});
