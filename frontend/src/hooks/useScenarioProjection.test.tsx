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
  it.each(cases)("loads %s directly for the selected scenario", async (_slug, hook, getter) => {
    vi.mocked(getter).mockResolvedValueOnce({} as never);
    renderHook(() => hook("scenario-a"), { wrapper });
    await waitFor(() => expect(getter).toHaveBeenCalledWith("scenario-a"));
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
