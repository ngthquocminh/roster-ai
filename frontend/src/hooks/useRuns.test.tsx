/**
 * RED-phase coverage for `useRuns` (Task 1, TDD). Mocks `@/api/runs` (module
 * boundary), never `msw`. Proves the hook is wired to the
 * `["runs", scenarioId]` query key / `listRuns`, and unit-tests the
 * `refetchInterval` predicate directly against RUNNING / all-terminal /
 * empty snapshots — the load-bearing self-terminating-poll behavior.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/runs", () => ({
  listRuns: vi.fn(),
}));

import { listRuns } from "@/api/runs";
import { useRuns } from "./useRuns";

const mockListRuns = listRuns as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  mockListRuns.mockReset();
});

describe("useRuns", () => {
  it("queries listRuns(scenarioId) under the ['runs', scenarioId] key and resolves to the list", async () => {
    const runs = [
      { id: "r1", scenario_id: "s1", status: "COMPLETED", created_at: "2026-01-01T00:00:00Z" },
    ];
    mockListRuns.mockResolvedValueOnce(runs);

    const { result } = renderHook(() => useRuns("s1"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockListRuns).toHaveBeenCalledWith("s1");
    expect(result.current.data).toEqual(runs);
  });

  it("surfaces isError (not a swallowed rejection) on a failed fetch", async () => {
    mockListRuns.mockRejectedValueOnce({ status: 404 });

    const { result } = renderHook(() => useRuns("s1"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 404 });
  });

  describe("refetchInterval predicate", () => {
    // Access the hook's queryFn/refetchInterval option directly by mounting
    // the hook and reading the resolved query's options via the query cache,
    // rather than re-implementing the predicate — the predicate under test
    // is the one actually wired into useQuery.
    async function mountAndGetPredicate(scenarioId: string) {
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false } },
      });
      function localWrapper({ children }: { children: ReactNode }) {
        return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
      }
      mockListRuns.mockResolvedValue([]);
      renderHook(() => useRuns(scenarioId), { wrapper: localWrapper });

      await waitFor(() => {
        const query = queryClient.getQueryCache().find({ queryKey: ["runs", scenarioId] });
        expect(query).toBeDefined();
      });

      const query = queryClient.getQueryCache().find({ queryKey: ["runs", scenarioId] })!;
      const options = query.options as { refetchInterval?: (q: typeof query) => number | false };
      expect(typeof options.refetchInterval).toBe("function");
      return { query, refetchInterval: options.refetchInterval! };
    }

    it("returns a positive poll interval when data has a non-terminal (RUNNING) run", async () => {
      const { query, refetchInterval } = await mountAndGetPredicate("s-running");
      query.setData([{ id: "r1", scenario_id: "s-running", status: "RUNNING", created_at: "x" }]);

      const result = refetchInterval(query);

      expect(typeof result).toBe("number");
      expect(result as number).toBeGreaterThan(0);
    });

    it("returns false when every run in data is terminal", async () => {
      const { query, refetchInterval } = await mountAndGetPredicate("s-terminal");
      query.setData([
        { id: "r1", scenario_id: "s-terminal", status: "COMPLETED", created_at: "x" },
        { id: "r2", scenario_id: "s-terminal", status: "FAILED", created_at: "x" },
      ]);

      expect(refetchInterval(query)).toBe(false);
    });

    it("returns false for an empty run list", async () => {
      const { query, refetchInterval } = await mountAndGetPredicate("s-empty");
      query.setData([]);

      expect(refetchInterval(query)).toBe(false);
    });
  });
});
