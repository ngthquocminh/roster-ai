import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApprovalDecisionPanel } from "./ApprovalDecisionPanel";

const mocks = vi.hoisted(() => ({ query: {} as any, mutation: {} as any }));
vi.mock("@/hooks/useApproval", () => ({ useApproval: () => mocks.query }));
vi.mock("@/hooks/useDecideApproval", () => ({ useDecideApproval: () => mocks.mutation }));

const approval = {
  approval_id: "11111111-1111-1111-1111-111111111111", state: "pending" as const,
  schedule_run_id: "22222222-2222-2222-2222-222222222222", candidate_schedule_version_id: "33333333-3333-3333-3333-333333333333",
  baseline_schedule_version: null, scenario_version_id: "44444444-4444-4444-4444-444444444444", consequence_summary: "Candidate replaces no current baseline.",
  policy_version: "policy-v1", agent_run_id: null,
  created_at: "2026-08-29T00:00:00Z", expires_at: "2099-08-29T01:00:00Z", resource_version: 1,
};

beforeEach(() => {
  mocks.query = { isPending: false, isError: false, isSuccess: true, data: approval };
  mocks.mutation = { isPending: false, isError: false, isSuccess: false, error: null, data: undefined, mutate: vi.fn() };
});

describe("ApprovalDecisionPanel", () => {
  it("fails closed while loading and errored", () => {
    mocks.query = { isPending: true, isError: false, isSuccess: false };
    const { rerender } = render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    mocks.query = { isPending: false, isError: true, isSuccess: false };
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
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, baseline_schedule_version: "baseline-v12" } };
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

  // The three-way NFR19/UX-DR35 distinctness assertion lives in
  // `test/accessibility-contract.test.tsx`, where the REAL `Composer` and
  // `DraftCard` can be rendered. Asserting it here meant inventing the two
  // other buttons, so the test chose the variants it then checked were
  // different -- and it picked `outline` for Run optimization, which DraftCard
  // actually ships as `secondary`.
  it("gives the baseline-moving control the destructive treatment", () => {
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByRole("button", { name: "Approve as baseline" })).toHaveAttribute("data-variant", "destructive");
    expect(screen.getByRole("button", { name: "Reject" })).toHaveAttribute("data-variant", "outline");
  });

  it("offers only dismissal for an overdue pending binding", () => {
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, expires_at: "2020-01-01T00:00:00Z" } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByRole("button", { name: /Dismiss expired approval request/ })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve as baseline" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject" })).not.toBeInTheDocument();
  });

  it.each(["rejected", "expired", "stale", "consumed"])("renders terminal %s without controls", (state) => {
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, state } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByText(`Terminal approval state: ${state}`)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Approve as baseline" })).not.toBeInTheDocument();
  });

  it("renders literal expected/current context after stale refusal", () => {
    mocks.mutation = { isPending: false, isError: true, isSuccess: false, mutate: vi.fn(), error: { code: "approval_stale", status: 409, expected: { policy_version: "v1" }, current: { policy_version: "v2" } } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByText(/Expected:.*v1/)).toBeInTheDocument();
    expect(screen.getByText(/Current:.*v2/)).toBeInTheDocument();
  });

  it("never renders an empty expected/current object as literal noise", () => {
    // `{}` is truthy in JavaScript, so the previous guard rendered `Expected: {}`
    // on every refusal that carries no version context.
    mocks.mutation = { isPending: false, isError: true, isSuccess: false, mutate: vi.fn(), error: { code: "promotion_not_available", status: 503, expected: {}, current: {} } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.queryByText(/Expected:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Current:/)).not.toBeInTheDocument();
  });

  it.each([
    ["approval_expired", 409, /had already expired/, /baseline did not change/],
    ["approval_stale", 409, /closed as stale/, /baseline did not change/],
    ["promotion_not_available", 503, /not available yet/, /still pending/],
    ["approval_not_pending", 409, /changed elsewhere/, /Refresh/],
  ])("tells the planner what actually happened for %s", (code, status, headline, detail) => {
    // Two of this endpoint's DESIGNED outcomes arrive as HTTP failures: the
    // dismissal succeeding (409 approval_expired) and every valid approve until
    // Story 4.3 (503). One undifferentiated "The approval changed" branch
    // reported both as the opposite of what the server did.
    mocks.mutation = { isPending: false, isError: true, isSuccess: false, mutate: vi.fn(), error: { code, status, expected: {}, current: {} } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    const live = screen.getByRole("status", { name: "Approval decision status" });
    expect(live).toHaveTextContent(headline);
    expect(live).toHaveTextContent(detail);
  });

  it("announces the committed outcome through a polite live region", () => {
    mocks.mutation = { isPending: false, isError: false, isSuccess: true, error: null, data: { ...approval, state: "rejected" }, mutate: vi.fn() };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    const live = screen.getByRole("status", { name: "Approval decision status" });
    expect(live).toHaveAttribute("aria-live", "polite");
    expect(live).toHaveTextContent(/Approval rejected/);
  });

  it("disables the expiry dismissal while its decision is in flight", () => {
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, expires_at: "2020-01-01T00:00:00Z" } };
    mocks.mutation = { isPending: true, isError: false, isSuccess: false, error: null, mutate: vi.fn() };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByRole("button", { name: /Dismiss expired approval request/ })).toBeDisabled();
  });

  it("keeps focus inside the panel when a committed decision unmounts the trigger", async () => {
    const user = userEvent.setup();
    const { rerender } = render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    const trigger = screen.getByRole("button", { name: "Reject" });
    await user.click(trigger);
    // The decision commits: the panel flips to its terminal branch and the
    // trigger unmounts, so Radix's restore target is a detached node.
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, state: "rejected" } };
    rerender(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    await user.keyboard("{Escape}");
    await vi.waitFor(() => expect(document.activeElement).not.toBe(document.body));
  });
});
