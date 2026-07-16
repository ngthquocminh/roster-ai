/**
 * RED-phase coverage for `useCreateScenario` (Task 1, TDD). Mocks
 * `../api/scenarios` (module boundary), never `msw`. The one link this test
 * exists to prove: `onSuccess` invalidates the exact `["scenarios"]` key
 * `useScenarios` reads — a byte-for-byte mismatch here means creation
 * succeeds silently and the new row never appears (this plan's single
 * highest-value link, per 01-07-PLAN.md).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/scenarios", () => ({
  createScenario: vi.fn(),
}));

import { createScenario } from "@/api/scenarios";
import { useCreateScenario } from "./useCreateScenario";

const mockCreateScenario = createScenario as unknown as ReturnType<
  typeof vi.fn
>;

beforeEach(() => {
  mockCreateScenario.mockReset();
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

describe("useCreateScenario", () => {
  it("mutates via createScenario and invalidates the ['scenarios'] query key byte-identical to useScenarios on success", async () => {
    const created = {
      id: "abc",
      name: "week1",
      fixture: "sample_tiny_input.json",
      time_limit_s: 60,
      created_at: "2026-01-01T00:00:00Z",
    };
    mockCreateScenario.mockResolvedValueOnce(created);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCreateScenario(), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate({ name: "week1", fixture: "sample_tiny_input.json" });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["scenarios"] });
  });

  it("does not invalidate anything, and reports isError, when createScenario rejects", async () => {
    mockCreateScenario.mockRejectedValueOnce({ status: 400, detail: "unknown fixture" });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useCreateScenario(), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate({ name: "week1", fixture: "does-not-exist.json" });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
  });

  it("propagates the rejected error, with its status intact, to the caller rather than swallowing it", async () => {
    mockCreateScenario.mockRejectedValueOnce({ status: 422, detail: "name required" });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderHook(() => useCreateScenario(), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate({ name: "", fixture: "sample_tiny_input.json" });

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(result.current.error).toMatchObject({ status: 422 });
  });

  it("does not insert anything into the ['scenarios'] cache before the server confirms (no optimistic update)", async () => {
    let resolveCreate: (value: unknown) => void = () => {};
    mockCreateScenario.mockReturnValueOnce(
      new Promise((resolve) => {
        resolveCreate = resolve;
      }),
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    queryClient.setQueryData(["scenarios"], []);

    const { result } = renderHook(() => useCreateScenario(), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate({ name: "week1", fixture: "sample_tiny_input.json" });

    // Still in flight: the cache must be untouched (still the seeded []).
    expect(queryClient.getQueryData(["scenarios"])).toEqual([]);

    resolveCreate({
      id: "abc",
      name: "week1",
      fixture: "sample_tiny_input.json",
      time_limit_s: 60,
      created_at: "2026-01-01T00:00:00Z",
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
});
