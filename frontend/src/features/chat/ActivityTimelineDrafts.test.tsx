/**
 * Story 5.11 Decision 13: the timeline mounts one live Draft card per proposal,
 * owns the unsaved edits, and tells the live card whether an agent turn runs.
 *
 * These render the REAL `DraftCard` (its hooks mocked, as in `DraftCard.test.tsx`)
 * so a moved card, a survived edit and a forwarded flag are observed on the page,
 * not asserted about a stub.
 */
import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useProposal");
vi.mock("@/hooks/useReviseProposal");
vi.mock("@/hooks/useRejectProposal");
vi.mock("@/hooks/useScenarioProjection");
vi.mock("@/hooks/useStartScheduleRun");

import { ActivityTimeline } from "./ActivityTimeline";
import * as proposalHooks from "@/hooks/useProposal";
import * as reviseHooks from "@/hooks/useReviseProposal";
import * as rejectHooks from "@/hooks/useRejectProposal";
import * as projectionHooks from "@/hooks/useScenarioProjection";
import * as startHooks from "@/hooks/useStartScheduleRun";
import { clearEvidenceUnavailable } from "@/features/evidence/availability";

const VERSION = "44444444-4444-4444-8444-444444444444";
const PROPOSAL_A = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const PROPOSAL_B = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const worker = {
  group: "workers" as const, record_id: "w1", label: "Alex (CONTACT-9)",
  scenario_version_id: VERSION, schema_version: "1",
};
const serverProposal = (proposalVersionId: string, versionOrdinal: number, hours = 40) => ({
  proposal_id: PROPOSAL_A, proposal_version_id: proposalVersionId,
  scenario_id: "33333333-3333-4333-8333-333333333333", scenario_version_id: VERSION,
  current_scenario_version_id: VERSION, expected_baseline_schedule_version: null,
  resolved_entities: [worker],
  constraints: [{
    kind: "set_max_hours" as const, resolved_entities: [worker], max_hours: hours,
    description: `Cap Alex (CONTACT-9) at ${hours} hours per week.`, schema_version: "1",
  }],
  preserved_locks: [], consequence_summary: `Cap at ${hours}.`,
  canonical_hash: "a".repeat(64), canonical_hash_algorithm: "sha256",
  canonical_hash_schema_version: "rfc8785-v1", state: "active" as const,
  resource_version: versionOrdinal, stale: false, version_ordinal: versionOrdinal,
  ended_by: null, applied_version_ordinal: null, schema_version: "1",
});

const draftActivity = (index: number, proposalId: string, summary: string) => ({
  schema_version: "1",
  activity_id: `cccccccc-cccc-4ccc-8ccc-${String(index).padStart(12, "0")}`,
  activity_type: "draft" as const,
  conversation_id: "22222222-2222-4222-8222-222222222222",
  conversation_resource_version: index + 1,
  scenario_id: "33333333-3333-4333-8333-333333333333", scenario_version_id: VERSION,
  occurred_at: "2026-08-10T00:00:00Z", sequence: String(index),
  proposal_id: proposalId,
  proposal_version_id: `dddddddd-dddd-4ddd-8ddd-${String(index).padStart(12, "0")}`,
  consequence_summary: summary,
});

function use(proposal: ReturnType<typeof serverProposal>) {
  vi.mocked(proposalHooks.useProposal).mockReturnValue({
    data: proposal, isPending: false, isError: false, error: null, refetch: vi.fn(),
  } as never);
}

beforeEach(() => {
  vi.clearAllMocks();
  clearEvidenceUnavailable();
  use(serverProposal("22222222-2222-4222-8222-222222222222", 1));
  vi.mocked(reviseHooks.useReviseProposal).mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
  vi.mocked(rejectHooks.useRejectProposal).mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
  vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({ mutate: vi.fn(), isPending: false } as never);
  vi.mocked(projectionHooks.useScenarioOverview).mockReturnValue({ data: { horizon_minutes: 10080 } } as never);
});

const timeline = (items: unknown[], props: { agentTurnInFlight?: boolean } = {}) => (
  <ActivityTimeline items={items as never} navigate={vi.fn()} {...props} />
);

describe("ActivityTimeline — one live Draft card per proposal", () => {
  it("mounts the live card on the newest draft activity only; older ones are one history line", () => {
    render(timeline([
      draftActivity(1, PROPOSAL_A, "First version summary"),
      draftActivity(2, PROPOSAL_A, "Second version summary"),
      draftActivity(3, PROPOSAL_A, "Third version summary"),
    ]));

    expect(screen.getAllByRole("region", { name: "Draft proposal" })).toHaveLength(1);
    const items = screen.getAllByRole("listitem");
    expect(within(items[0]).getByText("Earlier version of this draft · First version summary")).toBeInTheDocument();
    expect(within(items[1]).getByText("Earlier version of this draft · Second version summary")).toBeInTheDocument();
    expect(within(items[2]).getByRole("region", { name: "Draft proposal" })).toBeInTheDocument();
    expect(within(items[0]).queryByRole("region")).not.toBeInTheDocument();
    // History lines are plain content: nothing to press on them.
    expect(within(items[0]).queryByRole("button")).not.toBeInTheDocument();
  });

  it("keys the rule by proposal: two different drafts each keep their own live card", () => {
    render(timeline([
      draftActivity(1, PROPOSAL_A, "A"),
      draftActivity(2, PROPOSAL_B, "B"),
    ]));
    expect(screen.getAllByRole("region", { name: "Draft proposal" })).toHaveLength(2);
    expect(screen.queryByText(/Earlier version of this draft/)).not.toBeInTheDocument();
  });

  it("forwards the in-flight flag to the live card only", () => {
    render(timeline([
      draftActivity(1, PROPOSAL_A, "First"),
      draftActivity(2, PROPOSAL_A, "Second"),
    ], { agentTurnInFlight: true }));
    // Exactly one card carries the hint, and its controls are disabled.
    expect(screen.getAllByText("Wait for the assistant to finish")).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Discard draft" })).toBeDisabled();
  });

  it("keeps unsaved edits when the live card moves to a newer activity, and says the draft changed", async () => {
    const { rerender } = render(timeline([draftActivity(1, PROPOSAL_A, "v1")]));
    const input = screen.getByRole("spinbutton", { name: "Maximum hours" });
    await userEvent.clear(input);
    await userEvent.type(input, "33");
    expect(screen.getByRole("button", { name: "Save changes" })).toBeEnabled();

    // The assistant appends a version: a newer draft activity arrives, the live
    // card moves to a different <li> and the old instance unmounts.
    use(serverProposal("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee", 2, 44));
    rerender(timeline([draftActivity(1, PROPOSAL_A, "v1"), draftActivity(2, PROPOSAL_A, "v2")]));

    const items = screen.getAllByRole("listitem");
    expect(within(items[0]).getByText(/Earlier version of this draft/)).toBeInTheDocument();
    const moved = within(items[1]);
    // The local value survived the move (a card-local useState would have re-seeded to 44)...
    expect(moved.getByRole("spinbutton", { name: "Maximum hours" })).toHaveValue(33);
    // ...and the card says why Save is off instead of silently dropping the edit.
    expect(moved.getByText(/This draft changed to v2\. Your edits were not saved\./)).toBeInTheDocument();
    expect(moved.getByRole("button", { name: "Save changes" })).toBeDisabled();

    await userEvent.click(moved.getByRole("button", { name: "Load v2" }));
    expect(moved.getByRole("spinbutton", { name: "Maximum hours" })).toHaveValue(44);
    expect(moved.queryByText(/Your edits were not saved/)).not.toBeInTheDocument();
  });

  it("does not leak one proposal's edits into another's card", async () => {
    render(timeline([draftActivity(1, PROPOSAL_A, "A"), draftActivity(2, PROPOSAL_B, "B")]));
    const [first] = screen.getAllByRole("spinbutton", { name: "Maximum hours" });
    await userEvent.clear(first);
    await userEvent.type(first, "33");
    const [a, b] = screen.getAllByRole("spinbutton", { name: "Maximum hours" });
    // Buffers are keyed by the ACTIVITY's proposal id: only A's card shows the edit.
    expect(a).toHaveValue(33);
    expect(b).toHaveValue(40);
  });
});
