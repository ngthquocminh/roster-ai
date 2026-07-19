/**
 * RED-phase coverage for `useRunInsights` (Task 2, TDD). Mocks
 * `@/api/insights` (module boundary), never `msw`. Mirrors
 * `useTriggerRun.test.tsx`'s mutation-hook harness. Proves three things:
 * mutate() drives an idle -> pending -> success transition; a thrown 502
 * lands isError with `error.status === 502` and a second mutate() re-runs
 * (D-13 retry); and — the RES-05 isolation guarantee — no
 * `queryClient.invalidateQueries` call ever occurs, so an insight failure
 * structurally cannot touch the ['run', ...] query cache.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/insights", () => ({
  getRunInsights: vi.fn(),
}));

import { getRunInsights } from "@/api/insights";
import { useRunInsights } from "./useRunInsights";

const mockGetRunInsights = getRunInsights as unknown as ReturnType<
  typeof vi.fn
>;

beforeEach(() => {
  mockGetRunInsights.mockReset();
});

function makeWrapper(queryClient: QueryClient) {
  return function wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        {children}
      </QueryClientProvider>
    );
  };
}

describe("useRunInsights", () => {
  it("starts isIdle, then mutate() drives isPending -> isSuccess with data set", async () => {
    const insight = { ready: true, run_id: "r1", report: "All good." };
    mockGetRunInsights.mockResolvedValueOnce(insight);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderHook(() => useRunInsights("r1"), {
      wrapper: makeWrapper(queryClient),
    });

    expect(result.current.isIdle).toBe(true);

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetRunInsights).toHaveBeenCalledWith("r1");
    expect(result.current.data).toEqual(insight);
  });

  it("lands isError with error.status === 502 on a thrown 502, and a second mutate() re-runs", async () => {
    mockGetRunInsights.mockRejectedValueOnce({ status: 502 });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderHook(() => useRunInsights("r1"), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 502 });

    const insight = { ready: true, run_id: "r1", report: "Recovered." };
    mockGetRunInsights.mockResolvedValueOnce(insight);

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGetRunInsights).toHaveBeenCalledTimes(2);
    expect(result.current.data).toEqual(insight);
  });

  it("never calls queryClient.invalidateQueries, on success or on failure (RES-05 isolation)", async () => {
    mockGetRunInsights.mockResolvedValueOnce({
      ready: true,
      run_id: "r1",
      report: "ok",
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useRunInsights("r1"), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });
});
