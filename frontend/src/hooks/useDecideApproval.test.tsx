import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/approvals", () => ({ decideApproval: vi.fn() }));

import { decideApproval } from "@/api/approvals";
import { useDecideApproval } from "./useDecideApproval";

const mockDecide = vi.mocked(decideApproval);
const body = { decision: "approve" as const, expected_resource_version: 1 };
const consumed = {
  approval_id: "11111111-1111-1111-1111-111111111111",
  state: "consumed" as const,
  schedule_run_id: "22222222-2222-2222-2222-222222222222",
  candidate_schedule_version_id: "33333333-3333-3333-3333-333333333333",
  baseline_schedule_version: "baseline-v12",
  scenario_version_id: "44444444-4444-4444-4444-444444444444",
  consequence_summary: "Candidate replaces baseline-v12.",
  policy_version: "policy-v1",
  agent_run_id: null,
  created_at: "2026-08-29T00:00:00Z",
  expires_at: "2099-08-29T01:00:00Z",
  resource_version: 2,
};

describe("useDecideApproval", () => {
  it("invalidates approval, activity, comparison, and scenario views after promotion", async () => {
    const queryClient = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    mockDecide.mockResolvedValueOnce(consumed);
    const { result } = renderHook(() => useDecideApproval(consumed.approval_id), { wrapper });

    act(() => result.current.mutate(body));
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    for (const queryKey of [
      ["approval", consumed.approval_id],
      ["run-approvals"],
      ["conversation-timeline"],
      ["scheduleRunResult"],
      ["scenario-projection"],
    ]) expect(invalidate).toHaveBeenCalledWith({ queryKey });
  });
});
