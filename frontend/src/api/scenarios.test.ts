/**
 * SHELL-02 coverage for the three thin typed wrappers. Mocks at the `./client`
 * module boundary with `vi.mock` (not `msw` — see COVERAGE.md / RESEARCH.md;
 * `msw` is `[SLOP]`-rejected and its network-level interception is unneeded
 * for this 3-endpoint surface). The unit under test is each wrapper's
 * handling of the `{ data, error, response }` shapes `openapi-fetch` produces
 * — the mocked `client.GET`/`client.POST` calls return those shapes directly.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("./client", () => ({
  client: {
    GET: vi.fn(),
    POST: vi.fn(),
  },
}));

import { client } from "./client";
import { listScenarios, listFixtures, createScenario } from "./scenarios";

const mockGET = client.GET as unknown as ReturnType<typeof vi.fn>;
const mockPOST = client.POST as unknown as ReturnType<typeof vi.fn>;

beforeEach(() => {
  mockGET.mockReset();
  mockPOST.mockReset();
});

describe("listScenarios", () => {
  it("issues GET /scenarios and resolves to the response array", async () => {
    const rows = [
      { id: "a", name: "week1", fixture: "f.json", time_limit_s: 60, created_at: "2026-01-01T00:00:00Z" },
    ];
    mockGET.mockResolvedValueOnce({ data: rows, error: undefined, response: { status: 200 } });

    const result = await listScenarios();

    expect(mockGET).toHaveBeenCalledWith("/scenarios");
    expect(result).toEqual(rows);
  });

  it("resolves to [] (not null/undefined/throw) when the server returns an empty array", async () => {
    mockGET.mockResolvedValueOnce({ data: [], error: undefined, response: { status: 200 } });

    const result = await listScenarios();

    expect(result).toEqual([]);
    expect(result).not.toBeNull();
    expect(result).not.toBeUndefined();
  });

  it("preserves server order exactly, even with identical created_at values (no client-side sort)", async () => {
    const sharedCreatedAt = "2026-01-01T00:00:00Z";
    const rows = [
      { id: "c", name: "third", fixture: "f.json", time_limit_s: 60, created_at: sharedCreatedAt },
      { id: "a", name: "first", fixture: "f.json", time_limit_s: 60, created_at: sharedCreatedAt },
      { id: "b", name: "second", fixture: "f.json", time_limit_s: 60, created_at: sharedCreatedAt },
    ];
    mockGET.mockResolvedValueOnce({ data: rows, error: undefined, response: { status: 200 } });

    const result = await listScenarios();

    expect(result).toEqual(rows);
    expect(result?.map((r) => r.id)).toEqual(["c", "a", "b"]);
  });

  it("rejects (does not resolve to an error-shaped value) on a non-2xx response", async () => {
    mockGET.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "boom" },
      response: { status: 500 },
    });

    await expect(listScenarios()).rejects.toBeTruthy();
  });
});

describe("listFixtures", () => {
  it("issues GET /fixtures and resolves to the string array", async () => {
    const fixtures = ["sample_tiny_input.json"];
    mockGET.mockResolvedValueOnce({ data: fixtures, error: undefined, response: { status: 200 } });

    const result = await listFixtures();

    expect(mockGET).toHaveBeenCalledWith("/fixtures");
    expect(result).toEqual(fixtures);
  });
});

describe("createScenario", () => {
  it("issues POST /scenarios with a JSON body and resolves to the created ScenarioOut on 201", async () => {
    const body = { name: "week1", fixture: "sample_tiny_input.json" };
    const created = { id: "abc123", ...body, time_limit_s: 60, created_at: "2026-01-01T00:00:00Z" };
    mockPOST.mockResolvedValueOnce({ data: created, error: undefined, response: { status: 201 } });

    const result = await createScenario(body);

    // time_limit_s defaults to 60 (docs/API.md) when the caller omits it —
    // SCEN-02's UI never collects it.
    expect(mockPOST).toHaveBeenCalledWith("/scenarios", { body: { time_limit_s: 60, ...body } });
    expect(result).toEqual(created);
  });

  it("rejects with an error carrying status === 400 (unknown fixture)", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { detail: "fixture not found" },
      response: { status: 400 },
    });

    await expect(
      createScenario({ name: "week1", fixture: "does-not-exist.json" }),
    ).rejects.toMatchObject({ status: 400 });
  });

  it("rejects with an error carrying status === 422 (validation)", async () => {
    mockPOST.mockResolvedValueOnce({
      data: undefined,
      error: { detail: [{ msg: "field required" }] },
      response: { status: 422 },
    });

    await expect(
      createScenario({ name: "", fixture: "sample_tiny_input.json" }),
    ).rejects.toMatchObject({ status: 422 });
  });
});

describe("concurrency", () => {
  it("two concurrent calls each resolve with their own response; neither observes the other's", async () => {
    const scenarioRows = [
      { id: "a", name: "week1", fixture: "f.json", time_limit_s: 60, created_at: "2026-01-01T00:00:00Z" },
    ];
    const fixtureRows = ["sample_tiny_input.json"];

    mockGET.mockImplementation((path: string) => {
      if (path === "/scenarios") {
        return Promise.resolve({ data: scenarioRows, error: undefined, response: { status: 200 } });
      }
      if (path === "/fixtures") {
        return Promise.resolve({ data: fixtureRows, error: undefined, response: { status: 200 } });
      }
      throw new Error(`unexpected path: ${path}`);
    });

    const [scenarios, fixtures] = await Promise.all([listScenarios(), listFixtures()]);

    expect(scenarios).toEqual(scenarioRows);
    expect(fixtures).toEqual(fixtureRows);
  });
});
