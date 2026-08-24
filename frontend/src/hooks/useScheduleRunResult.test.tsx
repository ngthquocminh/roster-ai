import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/scheduleRuns", () => ({ getScheduleRunResult: vi.fn() }));

import { getScheduleRunResult } from "@/api/scheduleRuns";
import { scheduleRunResultKey, useScheduleRunResult } from "./useScheduleRunResult";

const mockGet = vi.mocked(getScheduleRunResult);

function wrapper({ children }: PropsWithChildren) {
  return <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}><MemoryRouter>{children}</MemoryRouter></QueryClientProvider>;
}

describe("useScheduleRunResult", () => {
  it("uses a stable key and stays disabled without a run id", () => {
    const { result } = renderHook(() => useScheduleRunResult(""), { wrapper });
    expect(scheduleRunResultKey("run-1")).toEqual(["scheduleRunResult", "run-1"]);
    expect(result.current.fetchStatus).toBe("idle");
    expect(mockGet).not.toHaveBeenCalled();
  });

  it("fetches the selected run", async () => {
    const value = { run: { schedule_run_id: "run-1", status: "solver_failed" }, candidate: null, comparison: null };
    mockGet.mockResolvedValueOnce(value as never);
    const { result } = renderHook(() => useScheduleRunResult("run-1"), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(mockGet).toHaveBeenCalledWith("run-1");
  });
});
