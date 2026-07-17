/**
 * Coverage for the applyConstraint wrapper. Mocks at the `./client` module
 * boundary with `vi.mock` (not `msw` — see scenarios.test.ts's own header
 * comment; msw is rejected for this codebase). The unit under test is the
 * wrapper's handling of the `{ data, error, response }` shapes
 * `openapi-fetch` produces — the mocked `client.POST` call returns those
 * shapes directly.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}));

import { client } from "./client";
import { applyConstraint } from "./constraints";

const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockPOST.mockReset();
});

describe("applyConstraint", () => {
  it("issues POST /constraints with a JSON body and resolves to the ConstraintParseResponse on 200", async () => {
    const body = { scenario_id: "abc123", text: "no more than 8 hours per shift" };
    const parsed = {
      applied: [{ id: "o1", tool: "set_max_hours", args: { hours: 8 }, parsed_constraint: "..." }],
      rejected: [],
      clarification_needed: null,
      no_constraint_found: false,
    };
    mockPOST.mockResolvedValueOnce({ data: parsed, error: undefined, response: { status: 200 } });

    const result = await applyConstraint(body);

    expect(mockPOST).toHaveBeenCalledWith("/constraints", { body });
    expect(result).toEqual(parsed);
  });

  it("rejects with an error carrying status === 503 (provider down)", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "LLM provider unavailable" },
      response: { status: 503 },
    });

    await expect(
      applyConstraint({ scenario_id: "abc123", text: "no more than 8 hours per shift" }),
    ).rejects.toMatchObject({ status: 503 });
  });

  it("rejects with an error carrying status === 422 (validation)", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { detail: [{ msg: "field required" }] },
      response: { status: 422 },
    });

    await expect(
      applyConstraint({ scenario_id: "", text: "" }),
    ).rejects.toMatchObject({ status: 422 });
  });
});
