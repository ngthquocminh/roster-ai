/**
 * RED-phase coverage for `useRunResult` (Task 1, TDD). Mocks `@/api/results`
 * (module boundary), never `msw`. Proves two things: the hook is wired to
 * the `["run", runId, "result"]` query key (a prefix-extension of `useRun`'s
 * `["run", runId]` key), and the dependent query never fires while
 * `enabled: false` — the mechanism that keeps the deep-linkable route from
 * ever hitting the pre-COMPLETED 409 (D-12, RESEARCH.md Pattern 1).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/results", () => ({
  getRunResult: vi.fn(),
}));

import { getRunResult } from "@/api/results";
import { useRunResult } from "./useRunResult";

const mockGetRunResult = getRunResult as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockGetRunResult.mockReset();
});

describe("useRunResult", () => {
  it("does not call getRunResult while enabled is false (dependent query stays idle, never 409s)", () => {
    const { result } = renderHook(
      () => useRunResult("r1", { enabled: false }),
      { wrapper },
    );

    expect(mockGetRunResult).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("queries getRunResult(id) under the ['run', id, 'result'] key once enabled is true", async () => {
    const runResult = {
      status: "COMPLETED",
      metrics: {
        total_cost: 100,
        total_unmet_hours: 0,
        scheduled_shifts: 5,
        scheduled_members: 3,
        coverage_by_function: {},
        coverage_by_day: {},
      },
      stats: {
        status: "OPTIMAL",
        wall_time_s: 1.2,
        unmet_objective_hours: 0,
        cost_objective: 100,
      },
      schedule: [],
      warnings: [],
    };
    mockGetRunResult.mockResolvedValueOnce(runResult);

    const { result } = renderHook(
      () => useRunResult("r1", { enabled: true }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetRunResult).toHaveBeenCalledWith("r1");
    expect(result.current.data).toEqual(runResult);
  });

  it("surfaces isError on a failed fetch when enabled", async () => {
    mockGetRunResult.mockRejectedValueOnce({ status: 409 });

    const { result } = renderHook(
      () => useRunResult("r1", { enabled: true }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 409 });
  });
});
