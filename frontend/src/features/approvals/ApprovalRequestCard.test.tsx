import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApprovalRequestCard } from "./ApprovalRequestCard";

const approval = {
  approval_id: "11111111-1111-1111-1111-111111111111",
  state: "pending" as const,
  schedule_run_id: "22222222-2222-2222-2222-222222222222",
  candidate_schedule_version_id: "33333333-3333-3333-3333-333333333333",
  baseline_schedule_version: null,
  scenario_version_id: "44444444-4444-4444-4444-444444444444",
  consequence_summary: "Candidate is ready for review.",
  policy_version: "one-user-mvp-v1+abcdef",
  expires_at: "2026-08-27T12:00:00Z",
};

describe("ApprovalRequestCard", () => {
  it("renders literal binding facts and presents an overdue pending request as expired", () => {
    render(<ApprovalRequestCard approval={approval} now={new Date("2026-08-27T13:00:00Z")} />);
    expect(screen.getByText("State: expired")).toBeInTheDocument();
    expect(screen.getByText("No current baseline")).toBeInTheDocument();
    expect(screen.getByText(approval.consequence_summary)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /approve|reject/i })).not.toBeInTheDocument();
  });

  it("renders the scenario version Task 10 requires", () => {
    render(<ApprovalRequestCard approval={approval} now={new Date("2026-08-27T11:00:00Z")} />);
    expect(screen.getByText("Scenario version")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: new RegExp(approval.scenario_version_id) }),
    ).toBeInTheDocument();
  });

  it("shows the agent-run identifier on the agent path and omits it on the planner path", () => {
    // AC2: "the same agent-run and approval identifiers remain visible".
    const agentRunId = "55555555-5555-5555-5555-555555555555";
    const { unmount } = render(
      <ApprovalRequestCard
        approval={{ ...approval, agent_run_id: agentRunId }}
        now={new Date("2026-08-27T11:00:00Z")}
      />,
    );
    expect(screen.getByText("Agent run ID")).toBeInTheDocument();
    unmount();

    // The planner path has no agent run, so the row is absent rather than empty.
    render(<ApprovalRequestCard approval={approval} now={new Date("2026-08-27T11:00:00Z")} />);
    expect(screen.queryByText("Agent run ID")).not.toBeInTheDocument();
  });
});
