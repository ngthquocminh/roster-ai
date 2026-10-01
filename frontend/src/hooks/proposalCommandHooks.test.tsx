/**
 * Story 5.11 Decision 14 (C9): the revise and reject hooks cache the response
 * body and then RE-READ the proposal. A replayed command answers "what did my
 * command do", so its body can be an old state; without the invalidation it
 * would stand as the current one.
 */
import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/scheduleRuns", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/scheduleRuns")>()),
  startScheduleRun: vi.fn(),
}));

vi.mock("@/api/proposals", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/proposals")>()),
  reviseProposal: vi.fn(),
  rejectProposal: vi.fn(),
}));

import { rejectProposal, reviseProposal } from "@/api/proposals";
import { startScheduleRun } from "@/api/scheduleRuns";
import { proposalKey } from "./useProposal";
import { useRejectProposal } from "./useRejectProposal";
import { useReviseProposal } from "./useReviseProposal";
import { useStartScheduleRun } from "./useStartScheduleRun";

const ID = "11111111-1111-4111-8111-111111111111";
const replayedBody = { proposal_id: ID, state: "active", version_ordinal: 2 } as never;

function setup() {
  const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  const invalidate = vi.spyOn(queryClient, "invalidateQueries");
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { queryClient, invalidate, wrapper };
}

describe("proposal command hooks", () => {
  it("useReviseProposal caches the body and then re-reads the proposal", async () => {
    const { queryClient, invalidate, wrapper } = setup();
    vi.mocked(reviseProposal).mockResolvedValueOnce(replayedBody);
    const { result } = renderHook(() => useReviseProposal(ID), { wrapper });

    act(() => result.current.mutate({ constraints: [], expected_resource_version: 1 } as never));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(queryClient.getQueryData(proposalKey(ID))).toBe(replayedBody);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: proposalKey(ID) });
  });

  it("useRejectProposal caches the body and then re-reads the proposal", async () => {
    const { queryClient, invalidate, wrapper } = setup();
    vi.mocked(rejectProposal).mockResolvedValueOnce(replayedBody);
    const { result } = renderHook(() => useRejectProposal(ID), { wrapper });

    act(() => result.current.mutate({ expected_resource_version: 1 }));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(queryClient.getQueryData(proposalKey(ID))).toBe(replayedBody);
    expect(invalidate).toHaveBeenCalledWith({ queryKey: proposalKey(ID) });
  });

  // Code review of story-5.11: a refusal the server answered settles the key, so
  // the planner's corrected Save is a new command, not an idempotency conflict;
  // a lost response keeps it, so a retry replays.
  it.each([
    ["a server-answered refusal", { status: 409, code: "stale_resource_version" }, false],
    ["a lost response", new TypeError("network"), true],
  ])("useReviseProposal after %s: same key next time = %s", async (_label, failure, sameKey) => {
    const { wrapper } = setup();
    vi.mocked(reviseProposal).mockReset();
    vi.mocked(reviseProposal).mockRejectedValueOnce(failure).mockResolvedValueOnce(replayedBody);
    const { result } = renderHook(() => useReviseProposal(ID), { wrapper });

    act(() => result.current.mutate({ constraints: [], expected_resource_version: 1 } as never));
    await waitFor(() => expect(result.current.isError).toBe(true));
    act(() => result.current.mutate({ constraints: [], expected_resource_version: 2 } as never));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const [first, second] = vi.mocked(reviseProposal).mock.calls.map((call) => call[2]);
    expect(first === second).toBe(sameKey);
  });

  it("useStartScheduleRun re-reads the proposal when the run is refused", async () => {
    const { invalidate, wrapper } = setup();
    vi.mocked(startScheduleRun).mockRejectedValueOnce({ status: 409, code: "applied_proposal" });
    const { result } = renderHook(() => useStartScheduleRun(), { wrapper });

    act(() => result.current.mutate({ proposal_id: ID, expected_resource_version: 3 } as never));
    await waitFor(() => expect(result.current.isError).toBe(true));

    expect(invalidate).toHaveBeenCalledWith({ queryKey: proposalKey(ID) });
  });
});
