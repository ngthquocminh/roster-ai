/**
 * RED-phase coverage for `useApplyConstraint` (Task 2, TDD). Mocks
 * `@/api/constraints` (module boundary), never `msw`. The one link this test
 * exists to prove: `onSuccess` invalidates the exact
 * `["scenario", id, "overrides"]` key `useOverrides` reads — and does NOT
 * invalidate `["scenario", id]` (the scenario-detail key), since `POST
 * /constraints` never changes `ScenarioOut` fields (RESEARCH Open Question
 * 2). A byte-for-byte mismatch here means applies succeed silently and the
 * overrides list never refetches (T-02-08).
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/constraints", () => ({
  applyConstraint: vi.fn(),
}));

import { applyConstraint } from "@/api/constraints";
import { useApplyConstraint } from "./useApplyConstraint";

const mockApplyConstraint = applyConstraint as unknown as ReturnType<
  typeof vi.fn
>;

beforeEach(() => {
  mockApplyConstraint.mockReset();
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

describe("useApplyConstraint", () => {
  it("mutates via applyConstraint({scenario_id, text}) and invalidates the ['scenario', id, 'overrides'] key on success — NOT the scenario-detail key", async () => {
    const response = {
      applied: [{ id: "c1", tool: "set_max_hours", args: {}, parsed_constraint: "..." }],
      rejected: [],
      clarification_needed: null,
      no_constraint_found: false,
    };
    mockApplyConstraint.mockResolvedValueOnce(response);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useApplyConstraint("abc"), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate("no more than 40 hours per week");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockApplyConstraint).toHaveBeenCalledWith({
      scenario_id: "abc",
      text: "no more than 40 hours per week",
    });
    expect(invalidateSpy).toHaveBeenCalledWith({
      queryKey: ["scenario", "abc", "overrides"],
    });
    expect(invalidateSpy).not.toHaveBeenCalledWith({
      queryKey: ["scenario", "abc"],
    });
  });

  it("does not invalidate anything, and reports isError, when applyConstraint rejects", async () => {
    mockApplyConstraint.mockRejectedValueOnce({ status: 503 });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useApplyConstraint("abc"), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate("no more than 40 hours per week");

    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidateSpy).not.toHaveBeenCalled();
    expect(result.current.error).toMatchObject({ status: 503 });
  });

  it("resolves the full ConstraintParseResponse to the caller (no textarea/transcript logic inside the hook)", async () => {
    const response = {
      applied: [],
      rejected: [{ tool: "unknown_tool", error: "not supported" }],
      clarification_needed: null,
      no_constraint_found: false,
    };
    mockApplyConstraint.mockResolvedValueOnce(response);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    const { result } = renderHook(() => useApplyConstraint("abc"), {
      wrapper: makeWrapper(queryClient),
    });

    result.current.mutate("some nonsense");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(response);
  });
});
