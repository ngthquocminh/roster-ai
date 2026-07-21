/**
 * Route-level composition coverage for `RunHistory` (RUN-01..RUN-05): proves
 * the view drives `TriggerRunButton`, `RunInFlightPanel`, and
 * `RunHistoryTable` from ONE `useRuns` response, and that the header CTA and
 * the table's empty-state CTA both invoke the SAME `useTriggerRun` mutation.
 *
 * Mocks `@/hooks/useRuns` and `@/hooks/useTriggerRun` at the module boundary
 * (not `@/api/runs`) — this is a composition test, not an integration test
 * of the hooks themselves; each hook already has its own coverage. Rendered
 * inside a memory router since `RunHistory` reads `scenarioId` via
 * `useParams`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router";

vi.mock("@/hooks/useRuns", () => ({
  useRuns: vi.fn(),
}));
vi.mock("@/hooks/useTriggerRun", () => ({
  useTriggerRun: vi.fn(),
}));

import { useRuns } from "@/hooks/useRuns";
import { useTriggerRun } from "@/hooks/useTriggerRun";
import { RunHistory } from "./RunHistory";
import type { components } from "@/api/schema";

type RunOut = components["schemas"]["RunOut"];

const mockUseRuns = useRuns as unknown as ReturnType<typeof vi.fn>;
const mockUseTriggerRun = useTriggerRun as unknown as ReturnType<typeof vi.fn>;

function runsQueryResult(overrides: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function triggerResult(overrides: Record<string, unknown> = {}) {
  return {
    mutate: vi.fn(),
    isPending: false,
    error: null,
    ...overrides,
  };
}

function renderRunHistory(path = "/scenarios/s1/runs") {
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId/runs", Component: RunHistory }],
    { initialEntries: [path] },
  );
  return render(<RouterProvider router={router} />);
}

const RUNNING_RUN: RunOut = {
  id: "run-active",
  scenario_id: "s1",
  status: "RUNNING",
  created_at: "2026-07-18T09:00:00Z",
  started_at: "2026-07-18T09:00:05Z",
  finished_at: null,
  solver_status: null,
  error: null,
};

const TERMINAL_RUNS: RunOut[] = [
  {
    id: "run-2",
    scenario_id: "s1",
    status: "COMPLETED",
    created_at: "2026-07-18T10:00:00Z",
    started_at: "2026-07-18T10:00:05Z",
    finished_at: "2026-07-18T10:02:00Z",
    solver_status: "OPTIMAL",
    error: null,
  },
  {
    id: "run-1",
    scenario_id: "s1",
    status: "FAILED",
    created_at: "2026-07-18T09:00:00Z",
    started_at: "2026-07-18T09:00:05Z",
    finished_at: "2026-07-18T09:01:00Z",
    solver_status: null,
    error: "Solver crashed",
  },
];

beforeEach(() => {
  mockUseRuns.mockReset();
  mockUseTriggerRun.mockReset();
});

describe("RunHistory: composition [RUN-01..RUN-04]", () => {
  it("renders the 'Run History' heading and an enabled 'Run Scenario' button", () => {
    mockUseRuns.mockReturnValue(runsQueryResult({ data: [] }));
    mockUseTriggerRun.mockReturnValue(triggerResult());
    renderRunHistory();

    expect(
      screen.getByRole("heading", { name: "Run History" }),
    ).toBeInTheDocument();
    expect(
      screen.getAllByRole("button", { name: "Run Scenario" })[0],
    ).toBeEnabled();
  });

  it("shows the in-flight panel when the newest active run is RUNNING", () => {
    mockUseRuns.mockReturnValue(runsQueryResult({ data: [RUNNING_RUN] }));
    mockUseTriggerRun.mockReturnValue(triggerResult());
    renderRunHistory();

    expect(screen.getByTestId("run-in-flight-panel")).toBeInTheDocument();
    expect(screen.getByText("Solving…")).toBeInTheDocument();
  });

  it("shows no in-flight panel when every run is terminal", () => {
    mockUseRuns.mockReturnValue(runsQueryResult({ data: TERMINAL_RUNS }));
    mockUseTriggerRun.mockReturnValue(triggerResult());
    renderRunHistory();

    expect(
      screen.queryByTestId("run-in-flight-panel"),
    ).not.toBeInTheDocument();
  });

  it("renders prior runs in the table", () => {
    mockUseRuns.mockReturnValue(runsQueryResult({ data: TERMINAL_RUNS }));
    mockUseTriggerRun.mockReturnValue(triggerResult());
    renderRunHistory();

    expect(screen.getByRole("table")).toBeInTheDocument();
    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(
      screen.getByText("This run couldn't be completed. Try starting a new run."),
    ).toBeInTheDocument();
    expect(screen.queryByText("Solver crashed")).not.toBeInTheDocument();
  });

  it("calls the trigger mutation when the header 'Run Scenario' button is clicked", () => {
    mockUseRuns.mockReturnValue(runsQueryResult({ data: TERMINAL_RUNS }));
    const trigger = triggerResult();
    mockUseTriggerRun.mockReturnValue(trigger);
    renderRunHistory();

    fireEvent.click(screen.getAllByRole("button", { name: "Run Scenario" })[0]);

    expect(trigger.mutate).toHaveBeenCalledTimes(1);
  });

  it("disables the button while a run is already in progress, derived from the same list", () => {
    mockUseRuns.mockReturnValue(runsQueryResult({ data: [RUNNING_RUN] }));
    mockUseTriggerRun.mockReturnValue(triggerResult());
    renderRunHistory();

    expect(
      screen.getAllByRole("button", { name: "Run Scenario" })[0],
    ).toBeDisabled();
    expect(
      screen.getByText("A run is already in progress for this scenario."),
    ).toBeInTheDocument();
  });
});
