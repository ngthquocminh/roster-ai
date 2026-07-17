/**
 * SCEN-03/D-01/D-02 overrides-list coverage (UI-SPEC E2). `OverridesList`
 * takes the raw `useOverrides(id, {enabled})` query-result object as a prop
 * (not a `scenarioId`), mirroring `ScenarioHeader`'s shape so plan 02-06's
 * `Editor` can pass the dependent-query result straight through.
 *
 * Copies `ScenarioTable.test.tsx`'s state-machine test shape. The populated
 * test asserts the raw `{tool, args}` JSON string never appears when
 * `parsed_constraint` is present (CONS-02 fidelity — must_haves prohibition).
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import type { UseQueryResult } from "@tanstack/react-query";

import { OverridesList } from "./OverridesList";
import type { components } from "@/api/schema";

type OverrideOut = components["schemas"]["OverrideOut"];

function queryResult(
  overrides: Partial<UseQueryResult<OverrideOut[], unknown>>,
): UseQueryResult<OverrideOut[], unknown> {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  } as UseQueryResult<OverrideOut[], unknown>;
}

describe("OverridesList: loading [UI-SPEC E2/loading]", () => {
  it("renders a centered spinner and 'Loading overrides…' with no rows", () => {
    render(<OverridesList overridesQuery={queryResult({ isLoading: true })} />);

    expect(screen.getByText("Loading overrides…")).toBeInTheDocument();
  });
});

describe("OverridesList: empty [UI-SPEC E2/empty]", () => {
  it("renders the empty-state heading and body", () => {
    render(<OverridesList overridesQuery={queryResult({ data: [] })} />);

    expect(
      screen.getByRole("heading", { name: "No constraints applied yet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Type a plain-English constraint below to add one."),
    ).toBeInTheDocument();
  });
});

describe("OverridesList: error [UI-SPEC E2/error]", () => {
  it("renders ErrorBanner and zero rows — no partial or stale rows", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    render(
      <OverridesList
        overridesQuery={queryResult({
          isError: true,
          error: new Error("network error"),
        })}
      />,
    );

    expect(
      screen.getByText("Can't reach the ShiftMind API."),
    ).toBeInTheDocument();

    vi.restoreAllMocks();
  });
});

describe("OverridesList: populated [UI-SPEC E2/populated, CONS-02]", () => {
  it("renders parsed_constraint verbatim and never the raw {tool, args} JSON", () => {
    const overrides: OverrideOut[] = [
      {
        id: "o1",
        tool: "set_max_hours",
        args: { member_id: "m1", max_hours: 40 },
        parsed_constraint: "Cap member m1 at 40 hours per week",
      },
    ];
    render(<OverridesList overridesQuery={queryResult({ data: overrides })} />);

    expect(
      screen.getByText("Cap member m1 at 40 hours per week"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText((_, node) =>
        Boolean(node?.textContent?.includes('"member_id"')),
      ),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/member_id=m1/)).not.toBeInTheDocument();
  });
});

describe("OverridesList: legacy fallback [UI-SPEC E2/partial, D-02 migration]", () => {
  it("renders the '{Tool Label}: key=value' fallback with a '(legacy entry)' caption when parsed_constraint is missing", () => {
    const overrides: OverrideOut[] = [
      {
        id: "o2",
        tool: "scale_demand",
        args: { factor: 1.2 },
        parsed_constraint: null,
      },
    ];
    render(<OverridesList overridesQuery={queryResult({ data: overrides })} />);

    expect(screen.getByText("Scale demand: factor=1.2")).toBeInTheDocument();
    expect(screen.getByText("(legacy entry)")).toBeInTheDocument();
  });

  it("falls back to the raw tool string for an unrecognized tool value", () => {
    const overrides: OverrideOut[] = [
      {
        id: "o3",
        tool: "some_future_tool",
        args: { x: 1 },
        parsed_constraint: undefined,
      },
    ];
    render(<OverridesList overridesQuery={queryResult({ data: overrides })} />);

    expect(screen.getByText("some_future_tool: x=1")).toBeInTheDocument();
  });
});

describe("OverridesList: zero-one-many [UI-SPEC E2/zero-one-many]", () => {
  it("renders one override with no count label anywhere", () => {
    const overrides: OverrideOut[] = [
      { id: "o1", tool: "set_max_hours", args: {}, parsed_constraint: "A" },
    ];
    const { container } = render(
      <OverridesList overridesQuery={queryResult({ data: overrides })} />,
    );

    expect(container.textContent).not.toMatch(/\b1 override\b/i);
    expect(container.textContent).not.toMatch(/overrides? \(/i);
  });

  it("renders many overrides in the exact order received, keyed by id (no client re-sort)", () => {
    const overrides: OverrideOut[] = [
      { id: "o1", tool: "set_max_hours", args: {}, parsed_constraint: "Third" },
      { id: "o2", tool: "scale_demand", args: {}, parsed_constraint: "First" },
      { id: "o3", tool: "lock_worker_shift", args: {}, parsed_constraint: "Second" },
    ];
    render(<OverridesList overridesQuery={queryResult({ data: overrides })} />);

    const rendered = screen.getAllByText(/^(Third|First|Second)$/);
    expect(rendered.map((el) => el.textContent)).toEqual([
      "Third",
      "First",
      "Second",
    ]);
  });
});
