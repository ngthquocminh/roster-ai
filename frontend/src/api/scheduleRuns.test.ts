import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}));

import { client } from "./client";
import { cancelScheduleRun, listScheduleRuns, startScheduleRun } from "./scheduleRuns";

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;
const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGET.mockReset();
  mockPOST.mockReset();
});

describe("startScheduleRun", () => {
  it("posts the version-bound proposal command with its stable idempotency key", async () => {
    const body = {
      proposal_id: "11111111-1111-1111-1111-111111111111",
      expected_resource_version: 3,
    };
    const responseBody = {
      schedule_run_id: "22222222-2222-2222-2222-222222222222",
      status: "solver_queued" as const,
      resource_version: 1,
    };
    mockPOST.mockResolvedValueOnce({
      data: responseBody,
      error: undefined,
      response: { status: 200 },
    });

    await expect(startScheduleRun(body, "stable-key")).resolves.toEqual(responseBody);
    expect(mockPOST).toHaveBeenCalledWith("/api/v1/schedule-runs", {
      params: { header: { "Idempotency-Key": "stable-key" } },
      body,
    });
  });

  it("attaches the HTTP status to problem details", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { code: "site_concurrency_exhausted" },
      response: { status: 429 },
    });

    await expect(
      startScheduleRun(
        {
          proposal_id: "11111111-1111-1111-1111-111111111111",
          expected_resource_version: 3,
        },
        "stable-key",
      ),
    ).rejects.toMatchObject({ status: 429, code: "site_concurrency_exhausted" });
  });
});

describe("listScheduleRuns", () => {
  it("gets a scenario's runs page with the query params it was given", async () => {
    const page = { items: [], next_cursor: null };
    mockGET.mockResolvedValueOnce({
      data: page,
      error: undefined,
      response: { status: 200 },
    });

    const params = { scenario_id: "11111111-1111-1111-1111-111111111111", cursor: 50, limit: 10 };
    await expect(listScheduleRuns(params)).resolves.toEqual(page);
    expect(mockGET).toHaveBeenCalledWith("/api/v1/schedule-runs", {
      params: { query: params },
    });
  });

  it("attaches the HTTP status to a list failure", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { code: "scenario_not_found" },
      response: { status: 404 },
    });

    await expect(
      listScheduleRuns({ scenario_id: "11111111-1111-1111-1111-111111111111" }),
    ).rejects.toMatchObject({ status: 404, code: "scenario_not_found" });
  });
});

describe("cancelScheduleRun", () => {
  it("posts the version-bound cancellation command with its stable idempotency key", async () => {
    const runId = "22222222-2222-2222-2222-222222222222";
    const body = { expected_resource_version: 3 };
    const responseBody = {
      schedule_run_id: runId,
      status: "cancellation_requested" as const,
      reason: "cancellation_requested",
      resource_version: 4,
      cancellation_requested: true,
    };
    mockPOST.mockResolvedValueOnce({
      data: responseBody,
      error: undefined,
      response: { status: 200 },
    });

    await expect(cancelScheduleRun(runId, body, "stable-key")).resolves.toEqual(responseBody);
    expect(mockPOST).toHaveBeenCalledWith("/api/v1/schedule-runs/{run_id}/cancellation", {
      params: {
        path: { run_id: runId },
        header: { "Idempotency-Key": "stable-key" },
      },
      body,
    });
  });

  it("attaches the HTTP status to a cancellation problem", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { code: "run_not_cancellable" },
      response: { status: 409 },
    });

    await expect(
      cancelScheduleRun(
        "22222222-2222-2222-2222-222222222222",
        { expected_resource_version: 3 },
        "stable-key",
      ),
    ).rejects.toMatchObject({ status: 409, code: "run_not_cancellable" });
  });
});
