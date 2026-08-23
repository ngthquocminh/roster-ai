import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/scheduleRuns", () => ({
  cancelScheduleRun: vi.fn(),
}));

import { cancelScheduleRun } from "@/api/scheduleRuns";
import { useCancelScheduleRun } from "./useCancelScheduleRun";

const mockCancel = vi.mocked(cancelScheduleRun);
const body = { expected_resource_version: 3 };
const cancelled = {
  schedule_run_id: "22222222-2222-2222-2222-222222222222",
  status: "cancellation_requested" as const,
  reason: "cancellation_requested",
  resource_version: 4,
  cancellation_requested: true,
};

describe("useCancelScheduleRun", () => {
  it("holds the same key across failure and rotates only after acknowledgement", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    mockCancel
      .mockRejectedValueOnce({ status: 409 })
      .mockResolvedValueOnce(cancelled)
      .mockResolvedValueOnce(cancelled);
    const { result } = renderHook(() => useCancelScheduleRun("run-1"), { wrapper });

    act(() => result.current.mutate(body));
    await waitFor(() => expect(result.current.isError).toBe(true));
    const failedKey = mockCancel.mock.calls[0][2];

    act(() => result.current.mutate(body));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockCancel.mock.calls[1][2]).toBe(failedKey);

    act(() => result.current.mutate(body));
    await waitFor(() => expect(mockCancel).toHaveBeenCalledTimes(3));
    expect(mockCancel.mock.calls[2][2]).not.toBe(failedKey);
  });

  it("invalidates the runs list on a successful cancellation", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    mockCancel.mockResolvedValueOnce(cancelled);
    const { result } = renderHook(() => useCancelScheduleRun("run-1"), { wrapper });

    act(() => result.current.mutate(body));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["scheduleRuns"] });
  });
});
