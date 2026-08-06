import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({ client: { GET: vi.fn() } }));

import { client } from "./client";
import {
  getBaselineAssignments,
  getConstraintsAndObjectives,
  getDemand,
  getLocks,
  getScenarioOverview,
  getWorkAreasAndTasks,
  getWorkers,
} from "./scenarioProjection";

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;
const success = { data: { group: "test" }, error: undefined, response: { status: 200 } };

beforeEach(() => mockGET.mockReset());

describe("scenario projection API", () => {
  it("gets the overview with a path parameter", async () => {
    mockGET.mockResolvedValueOnce(success);
    await getScenarioOverview("scenario-a");
    expect(mockGET).toHaveBeenCalledWith("/api/v1/scenarios/{scenario_id}/projection", {
      params: { path: { scenario_id: "scenario-a" } },
    });
  });

  it.each([
    ["work areas and tasks", getWorkAreasAndTasks, "/api/v1/scenarios/{scenario_id}/projection/work-areas-and-tasks"],
    ["workers", getWorkers, "/api/v1/scenarios/{scenario_id}/projection/workers"],
    ["demand", getDemand, "/api/v1/scenarios/{scenario_id}/projection/demand"],
    ["baseline assignments", getBaselineAssignments, "/api/v1/scenarios/{scenario_id}/projection/baseline-assignments"],
    ["locks", getLocks, "/api/v1/scenarios/{scenario_id}/projection/locks"],
    ["constraints", getConstraintsAndObjectives, "/api/v1/scenarios/{scenario_id}/projection/constraints-and-objectives"],
  ])("gets %s with optional paging params", async (_name, getter, path) => {
    mockGET.mockResolvedValueOnce(success);
    await getter("scenario-a", 5, 20);
    expect(mockGET).toHaveBeenCalledWith(path, {
      params: { path: { scenario_id: "scenario-a" }, query: { cursor: 5, limit: 20 } },
    });
  });

  it("omits undefined paging values and retains transport status on errors", async () => {
    mockGET.mockResolvedValueOnce({ data: undefined, error: { status: 500, code: "down" }, response: { status: 503 } });
    await expect(getWorkers("scenario-a")).rejects.toMatchObject({ status: 503, code: "down" });
    expect(mockGET).toHaveBeenCalledWith("/api/v1/scenarios/{scenario_id}/projection/workers", {
      params: { path: { scenario_id: "scenario-a" }, query: {} },
    });
  });

  it.each([
    ["overview", getScenarioOverview],
    ["work areas and tasks", getWorkAreasAndTasks],
    ["workers", getWorkers],
    ["demand", getDemand],
    ["baseline assignments", getBaselineAssignments],
    ["locks", getLocks],
    ["constraints", getConstraintsAndObjectives],
  ])("retains transport status for %s failures", async (_name, getter) => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { code: "projection_unavailable", status: 200 },
      response: { status: 503 },
    });
    await expect(getter("scenario-a")).rejects.toMatchObject({
      code: "projection_unavailable",
      status: 503,
    });
  });
});
