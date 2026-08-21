import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScheduleRuns", () => ({
  useScheduleRuns: vi.fn(),
}));
vi.mock("@/components/runs/RunsTable", () => ({
  RunsTable: (props: Record<string, unknown>) => (
    <div data-testid="runs-table" data-props={JSON.stringify({ ...props, onRetry: undefined })} />
  ),
}));

import { useScheduleRuns } from "@/hooks/useScheduleRuns";
import { ScenarioRuns } from "./ScenarioRuns";

const mockUseScheduleRuns = vi.mocked(useScheduleRuns);
const SCENARIO_ID = "33333333-3333-3333-3333-333333333333";
const refetch = vi.fn();

function renderRoute() {
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId/runs", Component: ScenarioRuns }],
    { initialEntries: [`/scenarios/${SCENARIO_ID}/runs`] },
  );
  return render(<RouterProvider router={router} />);
}

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ScenarioRuns", () => {
  it("passes loading state through to RunsTable", () => {
    mockUseScheduleRuns.mockReturnValue({
      data: undefined, isPending: true, isError: false, error: null, refetch,
    } as never);
    renderRoute();
    const props = JSON.parse(screen.getByTestId("runs-table").dataset.props ?? "{}");
    expect(props.isLoading).toBe(true);
    expect(props.runs).toEqual([]);
  });

  it("passes the fetched page's items through to RunsTable", () => {
    const items = [{ schedule_run_id: "run-1" }];
    mockUseScheduleRuns.mockReturnValue({
      data: { items, next_cursor: null }, isPending: false, isError: false, error: null, refetch,
    } as never);
    renderRoute();
    const props = JSON.parse(screen.getByTestId("runs-table").dataset.props ?? "{}");
    expect(props.runs).toEqual(items);
    expect(props.error).toBeNull();
  });

  it("surfaces a list failure as an error without unmounting the page heading (Trap 2)", () => {
    mockUseScheduleRuns.mockReturnValue({
      data: undefined, isPending: false, isError: true, error: { status: 500 }, refetch,
    } as never);
    renderRoute();
    expect(screen.getByRole("heading", { name: "Runs" })).toBeInTheDocument();
    const props = JSON.parse(screen.getByTestId("runs-table").dataset.props ?? "{}");
    expect(props.error).toEqual({ status: 500 });
  });

  it("does not show pagination controls on a single, first page", () => {
    mockUseScheduleRuns.mockReturnValue({
      data: { items: [], next_cursor: null }, isPending: false, isError: false, error: null, refetch,
    } as never);
    renderRoute();
    expect(screen.queryByRole("group", { name: "Run pages" })).not.toBeInTheDocument();
  });

  it("advances the query cursor via Next and back to 0 via First", async () => {
    const user = userEvent.setup();
    mockUseScheduleRuns.mockReturnValue({
      data: { items: [], next_cursor: 50 }, isPending: false, isError: false, error: null, refetch,
    } as never);
    renderRoute();

    // First call was with cursor 0 (Trap 6: page one never sends a stray cursor).
    expect(mockUseScheduleRuns).toHaveBeenCalledWith(SCENARIO_ID, 0);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(mockUseScheduleRuns).toHaveBeenLastCalledWith(SCENARIO_ID, 50);

    await user.click(screen.getByRole("button", { name: "First" }));
    expect(mockUseScheduleRuns).toHaveBeenLastCalledWith(SCENARIO_ID, 0);
  });
});
