/**
 * Route-level integration coverage for `ResultsView` (RES-01..RES-06, D-12).
 * Proves the D-12 three-way status branch (PENDING/RUNNING, FAILED,
 * COMPLETED) and — critically — the RES-05 failure-isolation guarantee: an
 * insight 502 re-renders only `InsightPanel`, leaving the coverage/chart/
 * schedule sections mounted and interactive.
 *
 * Mocks `@/hooks/useRun` and `@/hooks/useRunResult` at the module boundary
 * (not `msw`) — mirrors `RunHistory.test.tsx`'s composition-test convention:
 * this proves ResultsView's *branching*, not the hooks themselves (each
 * already has its own coverage). `InsightPanel` is NOT mocked — it mounts
 * for real, driven by a real `QueryClientProvider`, with only its underlying
 * `@/api/insights` wrapper mocked (mirrors `InsightPanel.test.tsx`'s own
 * harness) — this is what lets the RES-05 test drive a genuine 502 through
 * the real mutation lifecycle rather than a stubbed prop.
 *
 * Rendered inside a memory router at `/scenarios/s1/runs/r1` since
 * `ResultsView` reads `runId` via `useParams`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";
import type { ReactNode } from "react";

vi.mock("@/hooks/useRun", () => ({
  useRun: vi.fn(),
}));
vi.mock("@/hooks/useRunResult", () => ({
  useRunResult: vi.fn(),
}));
vi.mock("@/api/insights", () => ({
  getRunInsights: vi.fn(),
}));

import { useRun } from "@/hooks/useRun";
import { useRunResult } from "@/hooks/useRunResult";
import { getRunInsights } from "@/api/insights";
import { ResultsView } from "./ResultsView";
import type { components } from "@/api/schema";
import type { RunResult } from "@/api/results";

type RunOut = components["schemas"]["RunOut"];

const mockUseRun = useRun as unknown as ReturnType<typeof vi.fn>;
const mockUseRunResult = useRunResult as unknown as ReturnType<typeof vi.fn>;
const mockGetRunInsights = getRunInsights as unknown as ReturnType<
  typeof vi.fn
>;

function runQueryResult(overrides: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

function resultQueryResult(overrides: Record<string, unknown> = {}) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    isSuccess: false,
    ...overrides,
  };
}

const RUNNING_RUN: RunOut = {
  id: "r1",
  scenario_id: "s1",
  status: "RUNNING",
  created_at: "2026-07-18T09:00:00Z",
  started_at: "2026-07-18T09:00:05Z",
  finished_at: null,
  solver_status: null,
  error: null,
};

const FAILED_RUN: RunOut = {
  id: "r1",
  scenario_id: "s1",
  status: "FAILED",
  created_at: "2026-07-18T09:00:00Z",
  started_at: "2026-07-18T09:00:05Z",
  finished_at: "2026-07-18T09:01:00Z",
  solver_status: null,
  error: "Solver crashed",
};

const FAILED_RUN_NO_ERROR: RunOut = {
  ...FAILED_RUN,
  error: null,
};

const COMPLETED_RUN: RunOut = {
  id: "r1",
  scenario_id: "s1",
  status: "COMPLETED",
  created_at: "2026-07-18T09:00:00Z",
  started_at: "2026-07-18T09:00:05Z",
  finished_at: "2026-07-18T09:05:00Z",
  solver_status: "OPTIMAL",
  error: null,
};

// Hand-built against results.ts's RunResult interface (schema.d.ts has no
// type for this endpoint — see results.ts's own header-comment deviation).
const RUN_RESULT: RunResult = {
  status: "COMPLETED",
  metrics: {
    total_cost: 12345.5,
    total_unmet_hours: 3.5,
    scheduled_shifts: 2,
    scheduled_members: 2,
    coverage_by_function: {
      Pick: { required_h: 40, served_h: 38, pct: 0.95 },
      Receiving: { required_h: 10, served_h: 10, pct: 1.0 },
    },
    coverage_by_day: { "0": 0.95, "1": 1.0 },
  },
  stats: {
    status: "OPTIMAL",
    wall_time_s: 12.3,
    unmet_objective_hours: 3.5,
    cost_objective: 12345.5,
  },
  schedule: [
    {
      contact_id: "c1",
      member_name: "Alice",
      task_id: "t1",
      function: "Pick",
      shift_id: "sh1",
      start_h: 0,
      end_h: 8,
    },
    {
      contact_id: "c2",
      member_name: "Bob",
      task_id: "t2",
      function: "Receiving",
      shift_id: "sh2",
      start_h: 8,
      end_h: 16,
    },
  ],
  warnings: [],
};

function renderResultsView(path = "/scenarios/s1/runs/r1") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId/runs/:runId", Component: ResultsView }],
    { initialEntries: [path] },
  );
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  }
  return { ...render(<RouterProvider router={router} />, { wrapper: Wrapper }), router };
}

beforeEach(() => {
  mockUseRun.mockReset();
  mockUseRunResult.mockReset();
  mockGetRunInsights.mockReset();
});

describe("ResultsView: D-12 status gate [RES-01..RES-06]", () => {
  it("PENDING/RUNNING → renders RunInFlightPanel and no results body", () => {
    mockUseRun.mockReturnValue(runQueryResult({ data: RUNNING_RUN }));
    mockUseRunResult.mockReturnValue(resultQueryResult());
    renderResultsView();

    expect(screen.getByText("Solving…")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Run Results" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("FAILED (with error) → renders the 'Run Failed' alert with run.error and no results body", () => {
    mockUseRun.mockReturnValue(runQueryResult({ data: FAILED_RUN }));
    mockUseRunResult.mockReturnValue(resultQueryResult());
    renderResultsView();

    expect(screen.getByText("Run Failed")).toBeInTheDocument();
    expect(screen.getByText("Solver crashed")).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Run Results" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("FAILED (no error) → falls back to RunHistoryTable's exact FAILED_NO_ERROR_COPY", () => {
    mockUseRun.mockReturnValue(runQueryResult({ data: FAILED_RUN_NO_ERROR }));
    mockUseRunResult.mockReturnValue(resultQueryResult());
    renderResultsView();

    expect(
      screen.getByText("Failed — no error details were recorded."),
    ).toBeInTheDocument();
  });

  it("COMPLETED → renders coverage/chart/schedule/insight sections fed by resultQuery.data", () => {
    mockUseRun.mockReturnValue(runQueryResult({ data: COMPLETED_RUN }));
    mockUseRunResult.mockReturnValue(
      resultQueryResult({ data: RUN_RESULT, isSuccess: true }),
    );
    renderResultsView();

    expect(
      screen.getByRole("heading", { name: "Run Results" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Completed/)).toBeInTheDocument();
    // Coverage stat cards (D-04)
    expect(screen.getByText("Total Cost")).toBeInTheDocument();
    expect(screen.getByText("Total Unmet Hours")).toBeInTheDocument();
    // Coverage-by-day table (D-05) — coverage_by_day is a [0,1] fraction
    // (docs/API.md); assert the scaled percentage text, not just the label,
    // so this test actually guards against the CoverageByDayTable scaling
    // regression it previously missed (WR-01).
    expect(screen.getByText("Day 1")).toBeInTheDocument();
    expect(screen.getByText("95%")).toBeInTheDocument();
    expect(screen.getByText("100%")).toBeInTheDocument();
    // Schedule table (RES-03)
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Bob")).toBeInTheDocument();
    // Insight panel (RES-04), idle
    expect(
      screen.getByRole("button", { name: "Get Insight Report" }),
    ).toBeInTheDocument();
  });
});

describe("ResultsView: RES-05 insight failure isolation", () => {
  it("a 502 from the insight fetch shows the insight error while coverage/chart/schedule sections remain in the DOM", async () => {
    mockUseRun.mockReturnValue(runQueryResult({ data: COMPLETED_RUN }));
    mockUseRunResult.mockReturnValue(
      resultQueryResult({ data: RUN_RESULT, isSuccess: true }),
    );
    mockGetRunInsights.mockRejectedValueOnce({ status: 502 });
    renderResultsView();

    fireEvent.click(
      screen.getByRole("button", { name: "Get Insight Report" }),
    );

    await waitFor(() =>
      expect(
        screen.getByText("Couldn't generate an insight report right now."),
      ).toBeInTheDocument(),
    );

    // Sibling sections stay mounted and interactive — RES-05's hard
    // requirement — even while InsightPanel is showing its 502 state.
    expect(screen.getByText("Total Cost")).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getAllByRole("table").length).toBeGreaterThan(0);
  });
});

describe("ResultsView: CR-01 regression — insight report must not leak across runs", () => {
  it("navigating from run r1 to run r2 (param-only route change, no remount) does not keep r1's insight report visible under r2", async () => {
    mockUseRun.mockReturnValue(runQueryResult({ data: COMPLETED_RUN }));
    mockUseRunResult.mockReturnValue(
      resultQueryResult({ data: RUN_RESULT, isSuccess: true }),
    );
    mockGetRunInsights.mockResolvedValueOnce({
      ready: true,
      report: "REPORT FOR R1",
    });
    const { router } = renderResultsView("/scenarios/s1/runs/r1");

    fireEvent.click(
      screen.getByRole("button", { name: "Get Insight Report" }),
    );
    await waitFor(() =>
      expect(screen.getByText("REPORT FOR R1")).toBeInTheDocument(),
    );

    // React Router reuses the same ResultsView instance across a
    // param-only navigation on the same route pattern — this is the
    // exact re-render (not remount) that exposed CR-01.
    await router.navigate("/scenarios/s1/runs/r2");

    await waitFor(() =>
      expect(screen.queryByText("REPORT FOR R1")).not.toBeInTheDocument(),
    );
    expect(
      screen.getByRole("button", { name: "Get Insight Report" }),
    ).toBeInTheDocument();
  });
});
