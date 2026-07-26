import { beforeEach, describe, expect, it, vi } from "vitest";

const mockFetch = vi.fn();
let client: typeof import("./client").client;
let setCsrfToken: typeof import("./client").setCsrfToken;

beforeEach(async () => {
  mockFetch.mockReset();
  mockFetch.mockResolvedValue(new Response(null, { status: 204 }));
  vi.stubGlobal("fetch", mockFetch);
  vi.resetModules();
  ({ client, setCsrfToken } = await import("./client"));
  setCsrfToken(null);
});

describe("single API client session boundary", () => {
  it("includes the application cookie and cached CSRF token on unsafe requests", async () => {
    setCsrfToken("csrf-from-session");

    await client.POST("/api/v1/auth/logout");

    const request = mockFetch.mock.calls[0][0] as Request;
    expect(request.credentials).toBe("include");
    expect(request.headers.get("X-CSRF-Token")).toBe("csrf-from-session");
  });

  it("does not attach a CSRF token to safe requests", async () => {
    setCsrfToken("csrf-from-session");
    mockFetch.mockResolvedValue(
      new Response(
        JSON.stringify({
          app_user_id: "00000000-0000-0000-0000-000000000001",
          site_id: "00000000-0000-0000-0000-000000000002",
          csrf_token: "csrf-from-session",
          expires_at: "2030-01-01T00:00:00Z",
        }),
        {
          status: 200,
          headers: { "Content-Type": "application/json" },
        },
      ),
    );

    await client.GET("/api/v1/auth/session");

    const request = mockFetch.mock.calls[0][0] as Request;
    expect(request.credentials).toBe("include");
    expect(request.headers.has("X-CSRF-Token")).toBe(false);
  });
});
