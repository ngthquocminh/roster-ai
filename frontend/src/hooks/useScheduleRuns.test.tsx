import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/scheduleRuns", () => ({
  listScheduleRuns: vi.fn(),
}));

import { listScheduleRuns } from "@/api/scheduleRuns";
import { useScheduleRuns } from "./useScheduleRuns";

const mockList = vi.mocked(listScheduleRuns);

function wrapper({ children }: PropsWithChildren) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("useScheduleRuns", () => {
  it("stays disabled until a scenario id is present", () => {
    const { result } = renderHook(() => useScheduleRuns(""), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockList).not.toHaveBeenCalled();
  });

  it("fetches the page for the given scenario and cursor", async () => {
    const page = {
      scenario_id: "scenario-1",
      items: [],
      next_cursor: null,
      total_count: 0,
      matching_count: 0,
    };
    mockList.mockResolvedValueOnce(page);

    const { result } = renderHook(() => useScheduleRuns("scenario-1", 50), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockList).toHaveBeenCalledWith({ scenario_id: "scenario-1", cursor: 50 });
    expect(result.current.data).toEqual(page);
  });

  it("keeps the previous page rendered while the next one loads", async () => {
    // Without `keepPreviousData` a page turn changes the query key, `data`
    // drops to undefined, and the table is torn down to skeletons mid-fetch.
    const first = {
      scenario_id: "scenario-1",
      items: [],
      next_cursor: 50,
      total_count: 120,
      matching_count: 120,
    };
    mockList.mockResolvedValueOnce(first);
    const { result, rerender } = renderHook(
      ({ cursor }: { cursor: number }) => useScheduleRuns("scenario-1", cursor),
      { wrapper, initialProps: { cursor: 0 } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    let resolveSecond: (value: typeof first) => void = () => {};
    mockList.mockReturnValueOnce(new Promise((resolve) => { resolveSecond = resolve; }));
    rerender({ cursor: 50 });

    // Mid-flight: the previous page is still on screen, not undefined.
    expect(result.current.data).toEqual(first);
    expect(result.current.isPending).toBe(false);
    resolveSecond({ ...first, next_cursor: null });
    await waitFor(() => expect(result.current.data?.next_cursor).toBeNull());
  });
});
