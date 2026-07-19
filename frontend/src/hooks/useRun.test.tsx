/**
 * RED-phase coverage for `useRun` (Task 1, TDD). Mocks `@/api/runs` (module
 * boundary), never `msw`. Proves the hook is wired to the `["run", runId]`
 * query key and to `getRun` specifically, with no `enabled` gate — this is
 * the first, ungated fetch in the D-12 dependent-query chain.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/runs", () => ({
  getRun: vi.fn(),
}));

import { getRun } from "@/api/runs";
import { useRun } from "./useRun";

const mockGetRun = getRun as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockGetRun.mockReset();
});

describe("useRun", () => {
  it("queries getRun(id) under the ['run', id] key immediately, with no enabled gate", async () => {
    const run = {
      id: "r1",
      scenario_id: "s1",
      status: "COMPLETED",
      created_at: "2026-01-01T00:00:00Z",
    };
    mockGetRun.mockResolvedValueOnce(run);

    const { result } = renderHook(() => useRun("r1"), { wrapper });

    expect(result.current.fetchStatus).not.toBe("idle");

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetRun).toHaveBeenCalledWith("r1");
    expect(result.current.data).toEqual(run);
  });

  it("surfaces isError on a failed fetch", async () => {
    mockGetRun.mockRejectedValueOnce({ status: 404 });

    const { result } = renderHook(() => useRun("r1"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 404 });
  });
});
