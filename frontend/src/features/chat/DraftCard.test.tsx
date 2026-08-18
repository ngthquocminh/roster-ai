import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DraftCard } from "./DraftCard";
import * as proposalHooks from "@/hooks/useProposal";
import * as reviseHooks from "@/hooks/useReviseProposal";
import * as rejectHooks from "@/hooks/useRejectProposal";

vi.mock("@/hooks/useProposal");
vi.mock("@/hooks/useReviseProposal");
vi.mock("@/hooks/useRejectProposal");

const mutateRevision = vi.fn();
const mutateRejection = vi.fn();
const refetch = vi.fn();
const proposal = {
  proposal_id: "11111111-1111-4111-8111-111111111111",
  proposal_version_id: "22222222-2222-4222-8222-222222222222",
  scenario_id: "33333333-3333-4333-8333-333333333333",
  scenario_version_id: "44444444-4444-4444-8444-444444444444",
  current_scenario_version_id: "44444444-4444-4444-8444-444444444444",
  expected_baseline_schedule_version: "baseline-v1",
  resolved_entities: [{
    group: "workers" as const,
    record_id: "w1",
    label: "Alex (CONTACT-9)",
    scenario_version_id: "44444444-4444-4444-8444-444444444444",
    schema_version: "1",
  }],
  constraints: [{
    kind: "set_max_hours" as const,
    resolved_entities: [{
      group: "workers" as const,
      record_id: "w1",
      label: "Alex (CONTACT-9)",
      scenario_version_id: "44444444-4444-4444-8444-444444444444",
      schema_version: "1",
    }],
    max_hours: 40,
    description: "Cap Alex (CONTACT-9) at 40 hours per week.",
    schema_version: "1",
  }],
  preserved_locks: [{
    record_id: "lock-1", target_type: "worker", target_ref: "w1",
    scope: "assignment", source: "fixture", schema_version: "1",
  }],
  consequence_summary: "One reversible constraint; preserved one existing lock; no baseline change.",
  canonical_hash: "a".repeat(64),
  canonical_hash_algorithm: "sha256",
  canonical_hash_schema_version: "rfc8785-v1",
  state: "active" as const,
  resource_version: 1,
  stale: false,
  schema_version: "1",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(proposalHooks.useProposal).mockReturnValue({
    data: proposal, isPending: false, isError: false, error: null, refetch,
  } as never);
  vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({
    mutate: mutateRevision, isPending: false, isError: false,
  } as never);
  vi.mocked(rejectHooks.useRejectProposal).mockReturnValue({
    mutate: mutateRejection, isPending: false, isError: false,
  } as never);
});

describe("DraftCard", () => {
  it("renders the review contract and keeps revise/reject discontinuous from Send", async () => {
    render(<DraftCard proposalId={proposal.proposal_id} />);

    const region = screen.getByRole("region", { name: "Draft proposal" });
    expect(region).toHaveTextContent("Draft — no baseline change");
    expect(region).toHaveTextContent("Alex (CONTACT-9)");
    expect(region).toHaveTextContent("w1");
    expect(region).toHaveTextContent(proposal.constraints[0].description);
    expect(region).toHaveTextContent("lock-1");
    expect(region).toHaveTextContent(proposal.scenario_version_id);
    expect(region).toHaveTextContent("baseline-v1");
    expect(region).toHaveTextContent(proposal.consequence_summary);

    const revise = screen.getByRole("button", { name: "Revise proposal" });
    const reject = screen.getByRole("button", { name: "Reject proposal" });
    expect(revise).toHaveClass("min-h-11");
    expect(reject).toHaveClass("min-h-11");
    expect(revise.parentElement).not.toBe(reject.parentElement);
    expect(screen.queryByRole("button", { name: /run optimization/i })).not.toBeInTheDocument();

    await userEvent.clear(screen.getByRole("spinbutton", { name: "Maximum hours" }));
    await userEvent.type(screen.getByRole("spinbutton", { name: "Maximum hours" }), "36");
    await userEvent.click(revise);
    expect(mutateRevision).toHaveBeenCalledWith(expect.objectContaining({
      expected_resource_version: 1,
      constraints: [expect.objectContaining({ max_hours: 36 })],
    }));
    await userEvent.click(reject);
    expect(mutateRejection).toHaveBeenCalledWith({ expected_resource_version: 1 });
  });

  it("announces staleness, explains disabled revision, and offers only refresh", () => {
    vi.mocked(proposalHooks.useProposal).mockReturnValue({
      data: {
        ...proposal,
        stale: true,
        current_scenario_version_id: "55555555-5555-4555-8555-555555555555",
      },
      isPending: false, isError: false, error: null, refetch,
    } as never);

    render(<DraftCard proposalId={proposal.proposal_id} />);

    expect(screen.getByRole("status", { name: "Draft is stale" })).toBeInTheDocument();
    const revise = screen.getByRole("button", { name: "Revise proposal" });
    expect(revise).toBeDisabled();
    expect(revise).toHaveAccessibleDescription(/scenario version changed/i);
    expect(screen.getByRole("button", { name: "Refresh proposal" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject proposal" })).not.toBeInTheDocument();
  });
});
