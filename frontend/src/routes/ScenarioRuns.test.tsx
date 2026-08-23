import { render, screen, within } from "@testing-library/react";
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
      data: { items, next_cursor: null, total_count: 1, matching_count: 1 }, isPending: false, isError: false, error: null, refetch,
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

  it("renders the shared pager with every control disabled on a single, first page", () => {
    mockUseScheduleRuns.mockReturnValue({
      data: { items: [], next_cursor: null, total_count: 0, matching_count: 0 }, isPending: false, isError: false, error: null, refetch,
    } as never);
    renderRoute();
    const pager = screen.getByRole("group", { name: "Table pages" });
    for (const name of ["First", "Previous", "Next", "Last"]) {
      expect(within(pager).getByRole("button", { name })).toBeDisabled();
    }
  });

  it("hides the pager entirely while the first read is still in flight", () => {
    mockUseScheduleRuns.mockReturnValue({
      data: undefined, isPending: true, isError: false, error: null, refetch,
    } as never);
    renderRoute();
    expect(screen.queryByRole("group", { name: "Table pages" })).not.toBeInTheDocument();
  });

  it("advances the query cursor via Next, and steps back via Previous", async () => {
    const user = userEvent.setup();
    mockUseScheduleRuns.mockReturnValue({
      data: { items: [], next_cursor: 50, total_count: 120, matching_count: 120 }, isPending: false, isError: false, error: null, refetch,
    } as never);
    renderRoute();

    // First call was with cursor 0 (Trap 6: page one never sends a stray cursor).
    expect(mockUseScheduleRuns).toHaveBeenCalledWith(SCENARIO_ID, 0);

    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(mockUseScheduleRuns).toHaveBeenLastCalledWith(SCENARIO_ID, 50);

    // Previous is what the bespoke First/Next pair could not offer: without
    // total_count in the envelope the pager had no way to compute it.
    await user.click(screen.getByRole("button", { name: "Previous" }));
    expect(mockUseScheduleRuns).toHaveBeenLastCalledWith(SCENARIO_ID, 0);

    await user.click(screen.getByRole("button", { name: "Next" }));
    await user.click(screen.getByRole("button", { name: "Last" }));
    expect(mockUseScheduleRuns).toHaveBeenLastCalledWith(SCENARIO_ID, 100);
  });

  it("offers an explicit Refresh control on the success path that re-reads the list", async () => {
    // Nothing polls and no worker loop moves a run on its own yet, so the
    // planner needs a way to re-read the list that is not a page reload.
    // Before this existed, `refetch` was reachable only from the error branch.
    mockUseScheduleRuns.mockReturnValue({
      data: { items: [{ schedule_run_id: "run-1" }], next_cursor: null, total_count: 1, matching_count: 1 },
      isPending: false, isError: false, isFetching: false, error: null, refetch,
    } as never);
    renderRoute();

    await userEvent.click(screen.getByRole("button", { name: "Refresh" }));

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("disables Refresh while a read is already in flight", () => {
    mockUseScheduleRuns.mockReturnValue({
      data: { items: [], next_cursor: null, total_count: 0, matching_count: 0 },
      isPending: false, isError: false, isFetching: true, error: null, refetch,
    } as never);
    renderRoute();

    expect(screen.getByRole("button", { name: "Refreshing…" })).toBeDisabled();
  });
});
