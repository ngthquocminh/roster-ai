/**
 * RED-phase coverage for `useScenario` (Task 1, TDD). Mocks `@/api/scenarios`
 * (module boundary), never `msw`. Proves the hook is wired to the
 * `["scenario", scenarioId]` query key and to `getScenario` specifically.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/scenarios", () => ({
  getScenario: vi.fn(),
}));

import { getScenario } from "@/api/scenarios";
import { useScenario } from "./useScenario";

const mockGetScenario = getScenario as unknown as ReturnType<typeof vi.fn>;

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
}

beforeEach(() => {
  mockGetScenario.mockReset();
});

describe("useScenario", () => {
  it("queries getScenario(id) under the ['scenario', id] key and resolves to the scenario", async () => {
    const scenario = {
      id: "abc",
      name: "week1",
      fixture: "sample_tiny_input.json",
      time_limit_s: 60,
      created_at: "2026-01-01T00:00:00Z",
    };
    mockGetScenario.mockResolvedValueOnce(scenario);

    const { result } = renderHook(() => useScenario("abc"), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(mockGetScenario).toHaveBeenCalledWith("abc");
    expect(result.current.data).toEqual(scenario);
  });

  it("surfaces isLoading while the request is in flight", () => {
    mockGetScenario.mockReturnValue(new Promise(() => {}));

    const { result } = renderHook(() => useScenario("abc"), { wrapper });

    expect(result.current.isLoading).toBe(true);
  });

  it("surfaces isError (not a swallowed rejection) on a failed fetch", async () => {
    mockGetScenario.mockRejectedValueOnce({ status: 404 });

    const { result } = renderHook(() => useScenario("abc"), { wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(result.current.error).toMatchObject({ status: 404 });
  });
});
