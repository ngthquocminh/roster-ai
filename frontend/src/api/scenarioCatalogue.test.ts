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
});
