import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/button";
import { ApprovalDecisionPanel } from "./ApprovalDecisionPanel";

const mocks = vi.hoisted(() => ({ query: {} as any, mutation: {} as any }));
vi.mock("@/hooks/useApproval", () => ({ useApproval: () => mocks.query }));
vi.mock("@/hooks/useDecideApproval", () => ({ useDecideApproval: () => mocks.mutation }));

const approval = {
  approval_id: "11111111-1111-1111-1111-111111111111", state: "pending" as const,
  schedule_run_id: "22222222-2222-2222-2222-222222222222", candidate_schedule_version_id: "33333333-3333-3333-3333-333333333333",
  baseline_schedule_version: null, scenario_version_id: "44444444-4444-4444-4444-444444444444", consequence_summary: "Candidate replaces no current baseline.",
  policy_version: "policy-v1", parameter_hash: "a".repeat(64), consequence_hash: "b".repeat(64), agent_run_id: null,
  created_at: "2026-08-29T00:00:00Z", expires_at: "2099-08-29T01:00:00Z", resource_version: 1,
};

beforeEach(() => {
  mocks.query = { isPending: false, isError: false, data: approval };
  mocks.mutation = { isPending: false, isError: false, error: null, mutate: vi.fn() };
});

describe("ApprovalDecisionPanel", () => {
  it("fails closed while loading and errored", () => {
    mocks.query = { isPending: true, isError: false };
    const { rerender } = render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    mocks.query = { isPending: false, isError: true };
    rerender(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("opens a named confirmation dialog without mutating on the first click", async () => {
    const user = userEvent.setup(); render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    await user.click(screen.getByRole("button", { name: "Approve as baseline" }));
    expect(mocks.mutation.mutate).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Approve candidate as baseline" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Approve candidate .* replacing no current baseline/ })).toBeInTheDocument();
  });

  it("names a baseline replacement and restores focus after Escape and Cancel", async () => {
    const user = userEvent.setup();
    mocks.query = { isPending: false, isError: false, data: { ...approval, baseline_schedule_version: "baseline-v12" } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    const trigger = screen.getByRole("button", { name: "Approve as baseline" });
    await user.click(trigger);
    expect(screen.getByRole("button", { name: /replacing baseline-v12/ })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(trigger).toHaveFocus();
    await user.click(trigger);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(trigger).toHaveFocus();
    expect(mocks.mutation.mutate).not.toHaveBeenCalled();
  });

  it("keeps Send, Run optimization, and Approve as baseline semantically and visually distinct", () => {
    render(<><Button>Send</Button><Button variant="outline">Run optimization</Button><ApprovalDecisionPanel approvalId={approval.approval_id} /></>);
    const send = screen.getByRole("button", { name: "Send" });
    const run = screen.getByRole("button", { name: "Run optimization" });
    const approve = screen.getByRole("button", { name: "Approve as baseline" });
    expect(new Set([send.getAttribute("data-variant"), run.getAttribute("data-variant"), approve.getAttribute("data-variant")]).size).toBe(3);
  });

  it("offers only dismissal for an overdue pending binding", () => {
    mocks.query = { isPending: false, isError: false, data: { ...approval, expires_at: "2020-01-01T00:00:00Z" } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByRole("button", { name: /Dismiss expired approval request/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve as baseline" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  it.each(["rejected", "expired", "stale", "consumed"])("renders terminal %s without controls", (state) => {
    mocks.query = { isPending: false, isError: false, data: { ...approval, state } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByText(`Terminal approval state: ${state}`)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve as baseline" })).not.toBeInTheDocument();
  });

  it("renders literal expected/current context after stale refusal", () => {
    mocks.mutation = { isPending: false, isError: true, mutate: vi.fn(), error: { expected: { policy_version: "v1" }, current: { policy_version: "v2" } } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByText(/Expected:.*v1/)).toBeInTheDocument();
    expect(screen.getByText(/Current:.*v2/)).toBeInTheDocument();
  });
});
