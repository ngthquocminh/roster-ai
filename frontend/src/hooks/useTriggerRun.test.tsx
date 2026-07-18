/**
 * RED-phase coverage for `useTriggerRun` (Task 2, TDD). Mocks `@/api/runs`
 * (module boundary), never `msw`. The one link this test exists to prove:
 * `onSuccess` invalidates the exact `["runs", scenarioId]` key `useRuns`
 * reads — a byte-for-byte mismatch here means a triggered run silently
 * never appears (RUN-01).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/runs", () => ({
  triggerRun: vi.fn(),
}));

import { triggerRun } from "@/api/runs";
import { useTriggerRun } from "./useTriggerRun";

const mockTriggerRun = triggerRun as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockTriggerRun.mockReset();
});

function makeWrapper(queryClient: QueryClient) {
  return function wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe("useTriggerRun", () => {
  it("mutates via triggerRun(scenarioId) and invalidates exactly the ['runs', scenarioId] key on success", async () => {
    const run = {
      id: "r1",
      scenario_id: "s1",
      status: "PENDING",
      created_at: "2026-01-01T00:00:00Z",
    };
    mockTriggerRun.mockResolvedValueOnce(run);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useTriggerRun("s1"), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockTriggerRun).toHaveBeenCalledWith("s1");
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["runs", "s1"] });
    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(run);
  });

  it("does not invalidate anything, and reports isError with the status intact, when triggerRun rejects", async () => {
    mockTriggerRun.mockRejectedValueOnce({ status: 404 });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useTriggerRun("s1"), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate();

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(result.current.error).toMatchObject({ status: 404 });
  });
});
