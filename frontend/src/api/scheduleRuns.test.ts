import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({
  client: {
    POST: vi.fn(),
  },
}));

import { client } from "./client";
import { startScheduleRun } from "./scheduleRuns";

const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
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
