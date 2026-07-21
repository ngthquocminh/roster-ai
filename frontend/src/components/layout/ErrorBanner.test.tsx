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
  it("renders safe retry copy and keeps diagnostic-rich errors out of the DOM", () => {
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
    const diagnostic =
      "RuntimeError: solver crashed\n" +
      'File "C:\\srv\\backend\\services\\run_service.py", line 90\n' +
      "uv run uvicorn api.main:app --reload";
    const error = new Error(diagnostic);
    const { container } = render(<ErrorBanner error={error} />);

    expect(
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "Try again. If the problem continues, reload the page.",
      ),
    ).toBeInTheDocument();
    expect(container.textContent).not.toContain("RuntimeError");
    expect(container.textContent).not.toContain("run_service.py");
    expect(container.textContent).not.toContain("uv run uvicorn");
    expect(container.textContent).not.toContain("backend");
    expect(consoleError).toHaveBeenCalledWith(error);

    vi.restoreAllMocks();
  });

  it("renders the fixed copy when the error has an empty message [edge: SHELL-04/empty]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBanner error={new Error("")} />);

    expect(
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("renders the fixed copy when the error message is null/undefined [edge: SHELL-04/empty]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(<ErrorBanner error={{ message: null }} />);
    expect(
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();

    render(<ErrorBanner error={undefined} />);
    expect(
      screen.getAllByText("Couldn't load this content.").length,
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
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("never renders developer remediation for a non-Error input [edge: SHELL-04/encoding]", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const { container } = render(
      <ErrorBanner
        error={{
          message: "uv run uvicorn api.main:app --reload in backend/",
        }}
      />,
    );

    expect(container.textContent).not.toContain("uv run uvicorn");
    expect(container.textContent).not.toContain("backend/");
    expect(
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });
});
