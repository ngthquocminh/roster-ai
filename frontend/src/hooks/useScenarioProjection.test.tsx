import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/scenarioProjection", () => ({
  getScenarioOverview: vi.fn(),
  getWorkAreasAndTasks: vi.fn(),
  getWorkers: vi.fn(),
  getDemand: vi.fn(),
  getBaselineAssignments: vi.fn(),
  getLocks: vi.fn(),
  getConstraintsAndObjectives: vi.fn(),
}));

import * as api from "@/api/scenarioProjection";
import {
  useBaselineAssignments,
  useConstraintsAndObjectives,
  useDemand,
  useLocks,
  useScenarioOverview,
  useWorkAreasAndTasks,
  useWorkers,
} from "./useScenarioProjection";

const cases = [
  ["overview", useScenarioOverview, api.getScenarioOverview],
  ["work-areas-and-tasks", useWorkAreasAndTasks, api.getWorkAreasAndTasks],
  ["workers", useWorkers, api.getWorkers],
  ["demand", useDemand, api.getDemand],
  ["baseline-assignments", useBaselineAssignments, api.getBaselineAssignments],
  ["locks", useLocks, api.getLocks],
  ["constraints-and-objectives", useConstraintsAndObjectives, api.getConstraintsAndObjectives],
] as const;

function wrapper({ children }: { children: ReactNode }) {
  return (
    <MemoryRouter>
      <QueryClientProvider client={new QueryClient()}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

beforeEach(() => vi.clearAllMocks());

describe("scenario projection hooks", () => {
  it.each(cases)("loads %s directly for the selected scenario", async (slug, hook, getter) => {
    vi.mocked(getter).mockResolvedValueOnce({} as never);
    if (slug === "overview") {
      renderHook(() => hook("scenario-a"), { wrapper });
      await waitFor(() => expect(getter).toHaveBeenCalledWith("scenario-a"));
    } else {
      const listHook = hook as unknown as (scenarioId: string, params: { cursor: number }) => unknown;
      renderHook(() => listHook("scenario-a", { cursor: 5 }), { wrapper });
      await waitFor(() => expect(getter).toHaveBeenCalledWith("scenario-a", { cursor: 5 }));
    }
  });

  it("changes the demand query key when sort, filter, or cursor changes", async () => {
    vi.mocked(api.getDemand).mockResolvedValue({} as never);
    const queryClient = new QueryClient();
    const localWrapper = ({ children }: { children: ReactNode }) => (
      <MemoryRouter>
        <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
      </MemoryRouter>
    );
    const { rerender } = renderHook(
      ({ params }) => useDemand("scenario-a", params),
      {
        wrapper: localWrapper,
        initialProps: { params: { cursor: 0, sort: "start_minute" as const, family: "outbound" as const } },
      },
    );
    await waitFor(() => expect(api.getDemand).toHaveBeenCalledOnce());
    rerender({ params: { cursor: 50, sort: "start_minute", family: "outbound" } });
    await waitFor(() => expect(api.getDemand).toHaveBeenCalledTimes(2));

    expect(queryClient.getQueryCache().getAll().map((query) => query.queryKey)).toEqual(
      expect.arrayContaining([
        ["scenario-projection", "scenario-a", "demand", { cursor: 0, sort: "start_minute", family: "outbound" }],
        ["scenario-projection", "scenario-a", "demand", { cursor: 50, sort: "start_minute", family: "outbound" }],
      ]),
    );
  });

  it.each(cases)("disables %s when no scenario id exists", async (_slug, hook, getter) => {
    renderHook(() => hook(""), { wrapper });
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(getter).not.toHaveBeenCalled();
  });

  it.each(cases)("does not retry %s failures", async (_slug, hook, getter) => {
    vi.mocked(getter).mockRejectedValue(new Error("down"));
    const { result } = renderHook(() => hook("scenario-a"), { wrapper });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(getter).toHaveBeenCalledOnce();
  });
});
