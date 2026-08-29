import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useRequestApproval } from "./useRequestApproval";

const requestApproval = vi.fn();
vi.mock("@/api/approvals", () => ({
  requestApproval: (...args: unknown[]) => requestApproval(...args),
}));

function wrapper({ children }: Readonly<{ children: ReactNode }>) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

const body = {
  schedule_run_id: "11111111-1111-1111-1111-111111111111",
  expected_resource_version: 2,
  expected_baseline_schedule_version: null,
};

function keysUsed() {
  return requestApproval.mock.calls.map((call) => call[1] as string);
}

describe("useRequestApproval idempotency key lifecycle", () => {
  beforeEach(() => {
    requestApproval.mockReset();
  });

  it("rotates the key after a server-answered failure so a corrected retry is not a conflict", async () => {
    // The 409 path this surface actually tells the planner to take: the run
    // moved on, the UI says "Try again after refreshing the comparison", and
    // refreshing CHANGES `expected_resource_version`. Holding the original key
    // across that body change returns `409 idempotency_key_conflict` on every
    // subsequent attempt until the component unmounts -- the recovery the UI
    // recommends becomes permanently impossible.
    requestApproval.mockRejectedValueOnce({ status: 409, code: "stale_resource_version" });
    const { result } = renderHook(() => useRequestApproval(), { wrapper });

    result.current.mutate(body);
    await waitFor(() => expect(result.current.isError).toBe(true));

    requestApproval.mockResolvedValueOnce({ approval_id: "a" });
    result.current.mutate({ ...body, expected_resource_version: 3 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const [first, second] = keysUsed();
    expect(first).toBeTruthy();
    expect(second).toBeTruthy();
    expect(second).not.toEqual(first);
  });

  it("keeps the key when the server never answered, so a lost-response success replays", async () => {
    // The guarantee `idempotency.ts` exists for, and the reason settling on
    // EVERY error would be wrong: with no status we do not know whether the
    // command took effect, so the retry must carry the same key.
    requestApproval.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const { result } = renderHook(() => useRequestApproval(), { wrapper });

    result.current.mutate(body);
    await waitFor(() => expect(result.current.isError).toBe(true));

    requestApproval.mockResolvedValueOnce({ approval_id: "a" });
    result.current.mutate(body);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const [first, second] = keysUsed();
    expect(second).toEqual(first);
  });
});
