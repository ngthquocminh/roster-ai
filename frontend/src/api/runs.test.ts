/**
 * Coverage for the two thin typed run wrappers (RUN-01/RUN-02/RUN-04). Mocks
 * at the `./client` module boundary with `vi.mock` (not `msw` — see
 * scenarios.test.ts's own header comment; msw is rejected for this
 * codebase). The unit under test is each wrapper's handling of the
 * `{ data, error, response }` shapes `openapi-fetch` produces — the mocked
 * `client.GET`/`client.POST` calls return those shapes directly.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}));

import { client } from "./client";
import { listRuns, triggerRun } from "./runs";

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;
const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGET.mockReset();
  mockPOST.mockReset();
});

describe("listRuns", () => {
  it("issues GET /scenarios/{scenario_id}/runs with the scenario_id path param and resolves to the run array", async () => {
    const rows = [
      {
        id: "r1",
        scenario_id: "s1",
        status: "COMPLETED",
        created_at: "2026-01-01T00:00:00Z",
        started_at: "2026-01-01T00:00:01Z",
        finished_at: "2026-01-01T00:00:05Z",
        solver_status: "OPTIMAL",
        error: null,
      },
    ];
    mockGET.mockResolvedValueOnce({ data: rows, error: undefined, response: { status: 200 } });

    const result = await listRuns("s1");

    expect(mockGET).toHaveBeenCalledWith("/scenarios/{scenario_id}/runs", {
      params: { path: { scenario_id: "s1" } },
    });
    expect(result).toEqual(rows);
  });

  it("resolves to [] (not null/undefined/throw) when the server returns an empty array", async () => {
    mockGET.mockResolvedValueOnce({ data: [], error: undefined, response: { status: 200 } });

    const result = await listRuns("s1");

    expect(result).toEqual([]);
    expect(result).not.toBeNull();
    expect(result).not.toBeUndefined();
  });

  it("rejects with an error carrying status === 404", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "not found" },
      response: { status: 404 },
    });

    await expect(listRuns("does-not-exist")).rejects.toMatchObject({ status: 404 });
  });
});

describe("triggerRun", () => {
  it("issues POST /scenarios/{scenario_id}/runs with the scenario_id path param and resolves to the created RunOut on 201", async () => {
    const created = {
      id: "r1",
      scenario_id: "s1",
      status: "PENDING",
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      finished_at: null,
      solver_status: null,
      error: null,
    };
    mockPOST.mockResolvedValueOnce({ data: created, error: undefined, response: { status: 201 } });

    const result = await triggerRun("s1");

    expect(mockPOST).toHaveBeenCalledWith("/scenarios/{scenario_id}/runs", {
      params: { path: { scenario_id: "s1" } },
    });
    expect(result).toEqual(created);
  });

  it("rejects with an error carrying status === 404 (unknown scenario)", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "Scenario not found" },
      response: { status: 404 },
    });

    await expect(triggerRun("does-not-exist")).rejects.toMatchObject({ status: 404 });
  });
});
