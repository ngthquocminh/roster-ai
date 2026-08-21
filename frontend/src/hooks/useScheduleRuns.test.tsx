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
    const page = { items: [], next_cursor: null };
    mockList.mockResolvedValueOnce(page);

    const { result } = renderHook(() => useScheduleRuns("scenario-1", 50), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockList).toHaveBeenCalledWith({ scenario_id: "scenario-1", cursor: 50 });
    expect(result.current.data).toEqual(page);
  });
});
