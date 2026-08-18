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

  it("announces staleness, disables the REAL revise control, and still allows rejection", async () => {
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
    // The disabled control must be the one that would otherwise submit. An
    // earlier revision rendered a screen-reader-only, handler-less decoy button
    // when stale and left the real control unmounted, so this assertion passed
    // against an element that could never have been enabled.
    expect(revise).toHaveAttribute("type", "button");
    expect(revise.className).not.toMatch(/sr-only/);
    // Rejection changes no baseline and is the only terminal path a stale draft
    // has; hiding it stranded the proposal `active` forever after a reimport.
    const reject = screen.getByRole("button", { name: "Reject proposal" });
    expect(reject).toBeEnabled();
    await userEvent.click(reject);
    expect(mutateRejection).toHaveBeenCalledWith({ expected_resource_version: 1 });
  });

  it("surfaces a failed command instead of silently re-enabling the button", () => {
    vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({
      mutate: mutateRevision,
      isPending: false,
      error: { status: 409 },
    } as never);

    render(<DraftCard proposalId={proposal.proposal_id} />);

    // Four distinct RFC 7807 codes were built server-side and rendered by
    // nothing: the button un-disabled, the card did not change, and the planner
    // had no way to tell a refused command from a slow one.
    expect(
      screen.getByText(/changed since you opened it/i),
    ).toBeInTheDocument();
  });

  it("keeps a planner edit across a background refetch of the same version", async () => {
    const { rerender } = render(<DraftCard proposalId={proposal.proposal_id} />);

    const field = screen.getByRole("spinbutton", { name: "Maximum hours" });
    await userEvent.clear(field);
    await userEvent.type(field, "36");
    expect(screen.getByRole("spinbutton", { name: "Maximum hours" })).toHaveValue(36);

    // A refetch returns an equal-but-new object identity. Re-seeding on that
    // alone discarded whatever had been typed, with no indication -- and
    // TanStack refetches on window focus by default.
    vi.mocked(proposalHooks.useProposal).mockReturnValue({
      data: { ...proposal },
      isPending: false, isError: false, error: null, refetch,
    } as never);
    rerender(<DraftCard proposalId={proposal.proposal_id} />);

    expect(screen.getByRole("spinbutton", { name: "Maximum hours" })).toHaveValue(36);
  });

  it("sends only identifiers and numbers, never client-authored prose", async () => {
    render(<DraftCard proposalId={proposal.proposal_id} />);

    const field = screen.getByRole("spinbutton", { name: "Maximum hours" });
    await userEvent.clear(field);
    await userEvent.type(field, "36");
    await userEvent.click(screen.getByRole("button", { name: "Revise proposal" }));

    const body = mutateRevision.mock.calls.at(-1)?.[0];
    expect(body.constraints[0].max_hours).toBe(36);
    expect(body.constraints[0].record_id).toBe("w1");
    // The server recomposes these from the pinned projection. Echoing the old
    // description back persisted "40 hours" beside a 36-hour cap, and the card
    // rendered the stale number.
    expect(body.constraints[0]).not.toHaveProperty("description");
    expect(body.constraints[0]).not.toHaveProperty("resolved_entities");
  });

  it("shows both notices when a rejected proposal is also stale", () => {
    vi.mocked(proposalHooks.useProposal).mockReturnValue({
      data: {
        ...proposal,
        state: "rejected" as const,
        stale: true,
        current_scenario_version_id: "55555555-5555-4555-8555-555555555555",
      },
      isPending: false, isError: false, error: null, refetch,
    } as never);

    render(<DraftCard proposalId={proposal.proposal_id} />);

    // Testing `stale` first and returning made the rejected notice unreachable,
    // so Refresh was the only affordance and it re-rendered the same screen.
    expect(screen.getByRole("status", { name: "Draft is stale" })).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Draft is rejected" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Revise proposal" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Reject proposal" })).not.toBeInTheDocument();
  });

  it("renders the persisted summary while the proposal is still loading", () => {
    vi.mocked(proposalHooks.useProposal).mockReturnValue({
      data: undefined, isPending: true, isError: false, error: null, refetch,
    } as never);

    render(
      <DraftCard
        consequenceSummary={proposal.consequence_summary}
        proposalId={proposal.proposal_id}
      />,
    );

    // DraftActivityV1 persists the summary so the timeline can render a
    // reference immediately (Decision 6); discarding it left a bare spinner.
    expect(screen.getByRole("region", { name: "Draft proposal" }))
      .toHaveTextContent(proposal.consequence_summary);
  });
});
