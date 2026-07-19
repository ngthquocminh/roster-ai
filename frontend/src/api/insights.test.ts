/**
 * Coverage for the getRunInsights wrapper (RES-04/RES-05). Mocks at the
 * `./client` module boundary with `vi.mock` (not `msw` — see runs.test.ts's
 * own header comment). Asserts the success body passes through unmodified
 * (the wrapper never inspects `ready`) and that a 502 throws with
 * `.status === 502` attached.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
  },
}));

import { client } from "./client";
import { getRunInsights } from "./insights";

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGET.mockReset();
});

describe("getRunInsights", () => {
  it("issues GET /runs/{run_id}/insights with the run_id path param and resolves to the InsightOut body unmodified when ready", async () => {
    const body = { ready: true, run_id: "r1", report: "Overall, coverage reached 68%..." };
    mockGET.mockResolvedValueOnce({ data: body, error: undefined, response: { status: 200 } });

    const result = await getRunInsights("r1");

    expect(mockGET).toHaveBeenCalledWith("/runs/{run_id}/insights", {
      params: { path: { run_id: "r1" } },
    });
    expect(result).toEqual(body);
  });

  it("resolves the ready:false body as-is (does not throw, does not interpret 'ready')", async () => {
    const body = {
      ready: false,
      run_id: "r2",
      status: "RUNNING",
      reason: "Insights available only for COMPLETED runs (status: RUNNING)",
    };
    mockGET.mockResolvedValueOnce({ data: body, error: undefined, response: { status: 200 } });

    const result = await getRunInsights("r2");

    expect(result).toEqual(body);
  });

  it("rejects with an error carrying status === 502 (provider failure / grounding-guard rejection)", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "LLM provider failed" },
      response: { status: 502 },
    });

    await expect(getRunInsights("r3")).rejects.toMatchObject({ status: 502 });
  });

  it("rejects with an error carrying status === 404 (unknown run)", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "not found" },
      response: { status: 404 },
    });

    await expect(getRunInsights("does-not-exist")).rejects.toMatchObject({ status: 404 });
  });
});
