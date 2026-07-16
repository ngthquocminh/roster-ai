import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";

/**
 * Proves the Vitest + Testing Library + jsdom harness works end to end:
 * jsdom renders a component, and a jest-dom matcher (`toBeInTheDocument`) is
 * registered via src/test/setup.ts. Without this, a broken harness would
 * stay invisible until the first real component test (plan 01-05) failed
 * for a reason that looks like a component bug rather than a harness bug.
 */
describe("test harness smoke test", () => {
  it("renders in jsdom and a jest-dom matcher is registered", () => {
    render(<p>harness ok</p>);
    expect(screen.getByText("harness ok")).toBeInTheDocument();
  });
});
