import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
  },
}));

import { client } from "./client";
import {
  getScenarioContext,
  listFixtureVersions,
} from "./scenarioCatalogue";


const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGET.mockReset();
});

describe("scenario catalogue API", () => {
  it("lists fixture versions through the single generated client", async () => {
    const data = [{ scenario_id: "scenario-a" }];
    mockGET.mockResolvedValueOnce({
      data,
      error: undefined,
      response: { status: 200 },
    });

    await expect(listFixtureVersions()).resolves.toEqual(data);
    expect(mockGET).toHaveBeenCalledWith("/api/v1/scenarios");
  });

  it("opens context with a generated path parameter", async () => {
    const data = { scenario_id: "scenario-a" };
    mockGET.mockResolvedValueOnce({
      data,
      error: undefined,
      response: { status: 200 },
    });

    await expect(getScenarioContext("scenario-a")).resolves.toEqual(data);
    expect(mockGET).toHaveBeenCalledWith(
      "/api/v1/scenarios/{scenario_id}",
      { params: { path: { scenario_id: "scenario-a" } } },
    );
  });

  it("retains the HTTP status on failures", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { code: "authentication_required" },
      response: { status: 401 },
    });

    await expect(listFixtureVersions()).rejects.toMatchObject({
      status: 401,
      code: "authentication_required",
    });
  });

  it("keeps the transport status when the body carries its own", async () => {
    // ProblemDetailsV1 declares a required `status`, so a body spread after
    // response.status silently overwrote it and defeated the 401 redirect.
    // Omitting `status` from the mocked body made the test above unable to
    // catch that.
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { code: "authentication_required", status: 500 },
      response: { status: 401 },
    });

    await expect(listFixtureVersions()).rejects.toMatchObject({ status: 401 });
  });

  it("keeps the transport status on context failures too", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { code: "resource_not_found", status: 200 },
      response: { status: 404 },
    });

    await expect(getScenarioContext("scenario-a")).rejects.toMatchObject({
      status: 404,
    });
  });

  it("treats a bodyless 200 as an empty catalogue, not a failure", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: undefined,
      response: { status: 200 },
    });

    // Returning undefined here surfaces through TanStack as a query error,
    // rendering a connection failure for a successful response.
    await expect(listFixtureVersions()).resolves.toEqual([]);
  });
});
