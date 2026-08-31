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
    expect(screen.getByText(new RegExp(`Terminal approval state: ${state}`))).toBeInTheDocument();
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
    mocks.mutation = { isPending: false, isError: true, isSuccess: false, mutate: vi.fn(), error: { code: "approval_not_pending", status: 409, expected: {}, current: {} } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.queryByText(/Expected:/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Current:/)).not.toBeInTheDocument();
  });

  it.each([
    ["approval_expired", 409, /had already expired/, /baseline did not change/],
    ["approval_stale", 409, /closed as stale/, /baseline did not change/],
    ["approval_not_pending", 409, /changed elsewhere/, /Refresh/],
  ])("tells the planner what actually happened for %s", (code, status, headline, detail) => {
    // Terminalizing stale/expired outcomes arrive as HTTP failures even though
    // the governance state changed. One undifferentiated branch reported the
    // opposite of what the server did.
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

  it("names the promoted candidate and the baseline it replaced", () => {
    mocks.mutation = { isPending: false, isError: false, isSuccess: true, error: null, data: { ...approval, state: "consumed", baseline_schedule_version: "baseline-v12" }, mutate: vi.fn() };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByRole("status", { name: "Approval decision status" }))
      .toHaveTextContent(`${approval.candidate_schedule_version_id} is now the operational baseline, replacing baseline-v12`);
  });

  it("describes the moved pointer in the consumed terminal state", () => {
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, state: "consumed", baseline_schedule_version: "baseline-v12" } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByText(/promoted .* replacing baseline-v12/)).toBeInTheDocument();
  });

  it("says an agent-backed consumed approval RESUMED its run, never that it was cancelled", () => {
    // TX2 sets the run to `agent_running` on the approve edge (AD-7's "decision
    // recorded"); only the non-promoting terminal outcomes cancel it. Every
    // other fixture in this file pins `agent_run_id: null`, so the clause that
    // claimed a cancellation here was never exercised.
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, state: "consumed", agent_run_id: "run-1", baseline_schedule_version: "baseline-v12" } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.queryByText(/agent run was cancelled/)).not.toBeInTheDocument();
    expect(screen.getByText(/agent run was resumed/)).toBeInTheDocument();
  });

  it("still reports a cancelled run for the non-promoting terminal outcomes", () => {
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: { ...approval, state: "rejected", agent_run_id: "run-1" } };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByText(/agent run was cancelled/)).toBeInTheDocument();
  });

  it.each([
    ["stale_baseline_version", /operational baseline changed/],
    ["approval_payload_unreadable", /saved agent context could not be read/],
  ])("gives %s its own recovery copy instead of the generic retry advice", (code, expected) => {
    // Both are new 409/500 codes this story introduces. Falling to the default
    // arm told the planner to "try again", which cannot succeed -- the baseline
    // moved, so the pinned version will fail revalidation every time -- and
    // dropped the literal expected/current context the backend attaches.
    mocks.query = { isPending: false, isError: false, isSuccess: true, data: approval };
    mocks.mutation = { isPending: false, isError: true, isSuccess: false, error: { status: 409, code }, mutate: vi.fn() };
    render(<ApprovalDecisionPanel approvalId={approval.approval_id} />);
    expect(screen.getByText(expected)).toBeInTheDocument();
    expect(screen.queryByText(/The decision could not be submitted/)).not.toBeInTheDocument();
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
