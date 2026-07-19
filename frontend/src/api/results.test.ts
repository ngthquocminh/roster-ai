/**
 * Coverage for the hand-written RunResult wrapper (RES-01..RES-03, RES-06).
 * Mocks at the `./client` module boundary with `vi.mock` (not `msw` — see
 * runs.test.ts's own header comment). The unit under test is
 * getRunResult's handling of the `{ data, error, response }` shapes
 * `openapi-fetch` produces, plus that the mocked success body's `warnings`
 * array survives untouched through the one `as RunResult` cast point.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
  },
}));

import { client } from "./client";
import { getRunResult } from "./results";

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGET.mockReset();
});

describe("getRunResult", () => {
  it("issues GET /runs/{run_id}/result with the run_id path param and resolves to the RunResult body, warnings included", async () => {
    const body = {
      status: "OPTIMAL",
      metrics: {
        total_cost: 11806.41,
        total_unmet_hours: 212.13,
        scheduled_shifts: 40,
        scheduled_members: 10,
        coverage_by_function: {
          Pick: { required_h: 265.5, served_h: 94.1, pct: 0.354 },
        },
        coverage_by_day: { "0": 0.61, "1": 0.5 },
      },
      stats: {
        status: "OPTIMAL",
        wall_time_s: 8.0,
        unmet_objective_hours: 212.13,
        cost_objective: 11806.41,
      },
      schedule: [
        {
          contact_id: "AC0D87",
          member_name: "Rhiannon Hansen",
          task_id: "T123",
          function: "Pick",
          shift_id: "24_AC0D87_55",
          start_h: 5.5,
          end_h: 10.9,
        },
      ],
      warnings: ["Receiving has real demand but zero served hours."],
    };
    mockGET.mockResolvedValueOnce({ data: body, error: undefined, response: { status: 200 } });

    const result = await getRunResult("r1");

    expect(mockGET).toHaveBeenCalledWith("/runs/{run_id}/result", {
      params: { path: { run_id: "r1" } },
    });
    expect(result).toEqual(body);
    expect(result.warnings).toEqual(["Receiving has real demand but zero served hours."]);
  });

  it("resolves with an empty warnings array preserved as-is (not dropped, not defaulted elsewhere)", async () => {
    const body = {
      status: "OPTIMAL",
      metrics: {
        total_cost: null,
        total_unmet_hours: null,
        scheduled_shifts: 0,
        scheduled_members: 0,
        coverage_by_function: {},
        coverage_by_day: {},
      },
      stats: { status: "UNKNOWN", wall_time_s: null, unmet_objective_hours: null, cost_objective: null },
      schedule: [],
      warnings: [],
    };
    mockGET.mockResolvedValueOnce({ data: body, error: undefined, response: { status: 200 } });

    const result = await getRunResult("r2");

    expect(result.warnings).toEqual([]);
  });

  it("rejects with an error carrying status === 409 (run not COMPLETED yet)", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "Run not completed (status: RUNNING)" },
      response: { status: 409 },
    });

    await expect(getRunResult("r3")).rejects.toMatchObject({ status: 409 });
  });

  it("rejects with an error carrying status === 404 (unknown run)", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "not found" },
      response: { status: 404 },
    });

    await expect(getRunResult("does-not-exist")).rejects.toMatchObject({ status: 404 });
  });
});
