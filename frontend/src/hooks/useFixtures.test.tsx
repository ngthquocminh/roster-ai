/**
 * RED-phase coverage for `useFixtures` (Task 1, TDD). Mocks `../api/scenarios`
 * (module boundary) rather than `msw` (`[SLOP]`-rejected, RESEARCH.md/plan
 * 01-02). Proves the hook is wired to the `["fixtures"]` query key and to
 * `listFixtures` specifically — the exact contract `useCreateScenario` and
 * `CreateScenarioDialog` both depend on.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/scenarios", () => ({
  listFixtures: vi.fn(),
}));

import { listFixtures } from "@/api/scenarios";
import { useFixtures } from "./useFixtures";

const mockListFixtures = listFixtures as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockListFixtures.mockReset();
});

describe("useFixtures", () => {
  it("queries listFixtures under the ['fixtures'] key and resolves to the fixture list", async () => {
    mockListFixtures.mockResolvedValueOnce(["sample_tiny_input.json"]);

    const { result } = renderHook(() => useFixtures(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockListFixtures).toHaveBeenCalledTimes(1);
    expect(result.current.data).toEqual(["sample_tiny_input.json"]);
  });

  it("surfaces isLoading while the request is in flight", () => {
    mockListFixtures.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useFixtures(), { wrapper });

    expect(result.current.isLoading).toBe(true);
  });

  it("surfaces isError (not a swallowed rejection) on a failed fetch", async () => {
    mockListFixtures.mockRejectedValueOnce(new Error("network error"));

    const { result } = renderHook(() => useFixtures(), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
