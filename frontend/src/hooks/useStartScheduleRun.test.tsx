import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/scheduleRuns", () => ({
  startScheduleRun: vi.fn(),
}));

import { startScheduleRun } from "@/api/scheduleRuns";
import { useStartScheduleRun } from "./useStartScheduleRun";

const mockStart = vi.mocked(startScheduleRun);
const body = {
  proposal_id: "11111111-1111-1111-1111-111111111111",
  expected_resource_version: 3,
};
const queued = {
  schedule_run_id: "22222222-2222-2222-2222-222222222222",
  status: "solver_queued" as const,
  reason: null,
  resource_version: 1,
  cancellation_requested: false,
};

describe("useStartScheduleRun", () => {
  it("holds the same key across failure and rotates only after acknowledgement", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    mockStart
      .mockRejectedValueOnce({ status: 503 })
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce(queued);
    const { result } = renderHook(() => useStartScheduleRun(), { wrapper });

    act(() => result.current.mutate(body));
    await waitFor(() => expect(result.current.isError).toBe(true));
    const failedKey = mockStart.mock.calls[0][1];

    act(() => result.current.mutate(body));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockStart.mock.calls[1][1]).toBe(failedKey);

    act(() => result.current.mutate(body));
    await waitFor(() => expect(mockStart).toHaveBeenCalledTimes(3));
    expect(mockStart.mock.calls[2][1]).not.toBe(failedKey);
  });
});
