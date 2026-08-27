import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ApprovalRequestCard } from "./ApprovalRequestCard";

const approval = {
  approval_id: "11111111-1111-1111-1111-111111111111",
  state: "pending" as const,
  schedule_run_id: "22222222-2222-2222-2222-222222222222",
  candidate_schedule_version_id: "33333333-3333-3333-3333-333333333333",
  baseline_schedule_version: null,
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
});
