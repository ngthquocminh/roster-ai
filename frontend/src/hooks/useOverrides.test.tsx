/**
 * RED-phase coverage for `useOverrides` (Task 1, TDD). Mocks `@/api/scenarios`
 * (module boundary), never `msw`. Proves two things: the hook is wired to
 * the `["scenario", scenarioId, "overrides"]` query key (which
 * `useApplyConstraint`'s invalidation must byte-match), and the dependent
 * query never fires while `enabled: false`.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/scenarios", () => ({
  getScenarioOverrides: vi.fn(),
}));

import { getScenarioOverrides } from "@/api/scenarios";
import { useOverrides } from "./useOverrides";

const mockGetScenarioOverrides = getScenarioOverrides as unknown as ReturnType<
  typeof vi.fn
>;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockGetScenarioOverrides.mockReset();
});

describe("useOverrides", () => {
  it("does not call getScenarioOverrides while enabled is false (dependent query stays idle)", () => {
    const { result } = renderHook(
      () => useOverrides("abc", { enabled: false }),
      { wrapper },
    );

    expect(mockGetScenarioOverrides).not.toHaveBeenCalled();
    expect(result.current.isLoading).toBe(false);
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("queries getScenarioOverrides(id) under the ['scenario', id, 'overrides'] key once enabled is true", async () => {
    const overrides = [
      { id: "c1", tool: "set_max_hours", args: {}, parsed_constraint: "..." },
    ];
    mockGetScenarioOverrides.mockResolvedValueOnce(overrides);

    const { result } = renderHook(
      () => useOverrides("abc", { enabled: true }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetScenarioOverrides).toHaveBeenCalledWith("abc");
    expect(result.current.data).toEqual(overrides);
  });

  it("surfaces isError on a failed fetch when enabled", async () => {
    mockGetScenarioOverrides.mockRejectedValueOnce({ status: 500 });

    const { result } = renderHook(
      () => useOverrides("abc", { enabled: true }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 500 });
  });
});
