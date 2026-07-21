/**
 * SCEN-03 header coverage (UI-SPEC E1/E7). `ScenarioHeader` takes the raw
 * `useScenario(id)` query-result object as a prop (not a `scenarioId`) so
 * plan 02-06's `Editor` can share one `useScenario` instance between this
 * header and `useOverrides`'s `enabled` gate — see 02-04-PLAN.md Task 1.
 *
 * The 404 branch is asserted via a real `createMemoryRouter` (not a
 * `navigate` spy) — matching `ScenarioTable.test.tsx`'s convention — so the
 * "Back to Scenarios" link is proven to be a real route-capable anchor, not
 * just visible text.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { UseQueryResult } from "@tanstack/react-query";

import { ScenarioHeader } from "./ScenarioHeader";
import type { components } from "@/api/schema";

type ScenarioOut = components["schemas"]["ScenarioOut"];

function queryResult(
  overrides: Partial<UseQueryResult<ScenarioOut, unknown>>,
): UseQueryResult<ScenarioOut, unknown> {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  } as UseQueryResult<ScenarioOut, unknown>;
}

function renderHeader(scenarioQuery: UseQueryResult<ScenarioOut, unknown>) {
  const router = createMemoryRouter(
    [
      {
        path: "/scenarios/:scenarioId",
        Component: () => <ScenarioHeader scenarioQuery={scenarioQuery} />,
      },
      { path: "/", Component: () => <p>home-route</p> },
    ],
    { initialEntries: ["/scenarios/abc"] },
  );
  return render(<RouterProvider router={router} />);
}

describe("ScenarioHeader: loading [UI-SPEC E1/loading]", () => {
  it("renders a centered spinner and 'Loading scenario…' with no header fields", () => {
    renderHeader(queryResult({ isLoading: true }));

    expect(screen.getByText("Loading scenario…")).toBeInTheDocument();
    expect(screen.queryByRole("heading")).not.toBeInTheDocument();
  });
});

describe("ScenarioHeader: 404 [UI-SPEC E1/error-404, E7]", () => {
  it("renders the terminal 'Scenario not found' view with a 'Back to Scenarios' link routing to /", () => {
    renderHeader(queryResult({ isError: true, error: { status: 404 } }));

    expect(
      screen.getByRole("heading", { name: "Scenario not found" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("It may have been removed, or the link is incorrect."),
    ).toBeInTheDocument();
    const link = screen.getByRole("link", { name: "Back to Scenarios" });
    expect(link).toHaveAttribute("href", "/");
  });
});

describe("ScenarioHeader: non-404 error [UI-SPEC E1/error-network]", () => {
  it("renders ErrorBanner, not the 404 terminal view", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderHeader(queryResult({ isError: true, error: { status: 500 } }));

    expect(
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("Scenario not found"),
    ).not.toBeInTheDocument();

    vi.restoreAllMocks();
  });

  it("renders ErrorBanner when the error carries no status at all", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderHeader(queryResult({ isError: true, error: new Error("network error") }));

    expect(
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });
});

describe("ScenarioHeader: populated [UI-SPEC E1/populated]", () => {
  it("renders name (heading), fixture (monospace), time_limit_s, and created_at", () => {
    renderHeader(
      queryResult({
        data: {
          id: "abc",
          name: "Week 1",
          fixture: "sample_tiny_input.json",
          time_limit_s: 60,
          created_at: "2026-07-10T09:00:00Z",
        },
      }),
    );

    expect(
      screen.getByRole("heading", { name: "Week 1" }),
    ).toBeInTheDocument();
    const fixtureEl = screen.getByText("sample_tiny_input.json");
    expect(fixtureEl.className).toMatch(/font-mono/);
    expect(screen.getByText(/60/)).toBeInTheDocument();
    expect(screen.getByText(/2026-07-10T09:00:00Z/)).toBeInTheDocument();
  });
});
