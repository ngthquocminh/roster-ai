import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

// The panel reads the LIVE binding over the network, which is its own unit's
// concern (`ApprovalDecisionPanel.test.tsx`). This stub deliberately renders
// only the id it was handed: a stub that hardcoded the strings the assertions
// below look for would make them assertions about the stub, not the timeline.
vi.mock("@/features/approvals/ApprovalDecisionPanel", () => ({
  ApprovalDecisionPanel: ({ approvalId }: { approvalId: string }) => (
    <section aria-label="Approval request">
      <p>Live approval {approvalId}</p>
    </section>
  ),
}));

import { ActivityTimeline } from "./ActivityTimeline";
import { clearEvidenceUnavailable, markEvidenceUnavailable } from "@/features/evidence/availability";

beforeEach(() => clearEvidenceUnavailable());

const item = {
  schema_version: "1",
  activity_id: "11111111-1111-1111-1111-111111111111",
  activity_type: "planner_message" as const,
  conversation_id: "22222222-2222-2222-2222-222222222222",
  conversation_resource_version: 2,
  scenario_id: "33333333-3333-3333-3333-333333333333",
  scenario_version_id: "44444444-4444-4444-4444-444444444444",
  occurred_at: "2026-08-10T00:00:00Z",
  message_id: "55555555-5555-5555-5555-555555555555",
  text: "Check coverage",
  sequence: "1",
};

const second = {
  ...item,
  activity_id: "66666666-6666-6666-6666-666666666666",
  message_id: "77777777-7777-7777-7777-777777777777",
  text: "Then constraints",
  sequence: "2",
};

const agentResponse = {
  schema_version: "1",
  activity_id: "88888888-8888-8888-8888-888888888888",
  activity_type: "agent_response" as const,
  conversation_id: item.conversation_id,
  conversation_resource_version: 3,
  scenario_id: item.scenario_id,
  scenario_version_id: item.scenario_version_id,
  occurred_at: "2026-08-10T00:00:01Z",
  sequence: "2",
  response: {
    schema_version: "1",
    scenario_version_id: item.scenario_version_id,
    segments: [
      { schema_version: "1", kind: "prose" as const, text: "Coverage has a shortfall of" },
      {
        schema_version: "1",
        kind: "claim" as const,
        metric: "staffed_minutes" as const,
        arguments: {
          schema_version: "1",
          task_id: "pick",
          family: "outbound" as const,
          start_minute: 780,
          end_minute: 1020,
        },
        result_id: "result-1",
        value: 45,
        unit: "minutes" as const,
        verdict: "supported" as const,
        failure: null,
        evidence_refs: [
          {
            schema_version: "1",
            scenario_version_id: item.scenario_version_id,
            checksum_algorithm: "sha256",
            checksum_schema_version: "1",
            checksum_digest: "a".repeat(64),
            producing_run_version: null,
            baseline_schedule_version: null,
            group: "demand" as const,
            record_id: "DEM-204",
            field: "amount",
            start_minute: 780,
            end_minute: 1020,
          },
        ],
      },
      {
        schema_version: "1",
        kind: "claim" as const,
        metric: "qualified_worker_count" as const,
        arguments: { schema_version: "1" },
        result_id: "result-2",
        value: null,
        unit: null,
        verdict: "failed" as const,
        failure: "version_mismatch" as const,
        evidence_refs: [],
      },
    ],
  },
};

const clarification = {
  ...item,
  activity_id: "99999999-9999-9999-9999-999999999999",
  activity_type: "clarification" as const,
  sequence: "3",
  clarification: {
    schema_version: "1",
    question: "Which worker did you mean?",
    scenario_version_id: item.scenario_version_id,
    dropped_candidate_count: 1,
    candidates: [
      {
        schema_version: "1",
        group: "workers" as const,
        record_id: "w1",
        label: "CONTACT-9",
        scenario_version_id: item.scenario_version_id,
      },
    ],
  },
};

const refusal = {
  ...item,
  activity_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  activity_type: "terminal_outcome" as const,
  sequence: "4",
  outcome: {
    schema_version: "1",
    status: "completed" as const,
    reason: "refused" as const,
    detail: "That capability is not available.",
    next_step: "Review Scenario Data.",
  },
};

const approvalRequest = {
  ...item,
  activity_id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
  activity_type: "approval_request" as const,
  sequence: "5",
  approval_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
  approval_state: "pending" as const,
  agent_run_id: "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee",
  schedule_run_id: "ffffffff-ffff-ffff-ffff-ffffffffffff",
  candidate_schedule_version_id: "12121212-1212-1212-1212-121212121212",
  baseline_schedule_version: null,
  consequence_summary: "Candidate is ready for review.",
  parameter_hash: "a".repeat(64),
  consequence_hash: "b".repeat(64),
  policy_version: "one-user-mvp-v1+abcdef",
  expires_at: "2999-08-27T12:00:00Z",
};

function renderedIds() {
  return screen
    .getAllByRole("listitem")
    .map((node) => node.getAttribute("data-activity-id"));
}

describe("ActivityTimeline", () => {
  it("renders an approval request once from its persisted activity", () => {
    render(<ActivityTimeline navigate={vi.fn()} items={[approvalRequest, approvalRequest]} />);
    expect(screen.getAllByRole("region", { name: "Approval request" })).toHaveLength(1);
    expect(screen.getByText(/Live approval dddddddd-dddd-dddd-dddd-dddddddddddd/)).toBeInTheDocument();
  });

  it.each(["rejected", "expired", "stale", "consumed"] as const)(
    "renders a terminal %s payload as a compact line, never a second panel",
    (state) => {
      render(
        <ActivityTimeline
          navigate={vi.fn()}
          items={[{ ...approvalRequest, activity_id: "13131313-1313-1313-1313-131313131313", approval_state: state }]}
        />,
      );
      expect(screen.getByText(`Approval ${state} · dddddddd-dddd-dddd-dddd-dddddddddddd`)).toBeInTheDocument();
      expect(screen.queryByRole("region", { name: "Approval request" })).not.toBeInTheDocument();
    },
  );

  it("stops rendering the live panel on the superseded pending activity once a decision arrives", () => {
    // TX1 appends a `pending` activity; TX3 appends a SECOND one carrying the
    // terminal state with a fresh `activity_id`. Dedupe is keyed on event
    // identity (UX-DR6), so both survive -- and before this rule the older
    // event went on mounting a live panel above the newer terminal line.
    const terminal = {
      ...approvalRequest,
      activity_id: "14141414-1414-1414-1414-141414141414",
      sequence: "6",
      approval_state: "rejected" as const,
    };
    render(<ActivityTimeline navigate={vi.fn()} items={[approvalRequest, terminal]} />);
    expect(renderedIds()).toHaveLength(2);
    expect(screen.queryByRole("region", { name: "Approval request" })).not.toBeInTheDocument();
    expect(screen.getByText(/Approval pending · dddddddd/)).toBeInTheDocument();
    expect(screen.getByText(/Approval rejected · dddddddd/)).toBeInTheDocument();
  });
  it("builds the jump only from the persisted locator and activity scenario", () => {
    const navigate = vi.fn();
    render(<ActivityTimeline items={[agentResponse]} navigate={navigate} />);

    screen.getByRole("button", { name: /Evidence: demand DEM-204/ }).click();

    expect(navigate).toHaveBeenCalledWith(
      `/scenarios/${agentResponse.scenario_id}/data?group=demand&record=DEM-204&version=${agentResponse.scenario_version_id}&field=amount&start=780&end=1020`,
      { state: { evidenceOrigin: {
        conversationId: agentResponse.conversation_id,
        activityId: agentResponse.activity_id,
        segmentIndex: 1,
        refIndex: 0,
      } } },
    );
  });

  it("keeps a supported historical claim visible while marking lost evidence unavailable", () => {
    markEvidenceUnavailable({
      conversationId: agentResponse.conversation_id,
      activityId: agentResponse.activity_id,
      segmentIndex: 1,
      refIndex: 0,
    });
    render(<ActivityTimeline navigate={vi.fn()} items={[agentResponse]} />);

    expect(screen.getByText("45 minutes")).toBeInTheDocument();
    expect(screen.getByText("Evidence unavailable")).toBeInTheDocument();
  });
  it("deduplicates replayed activity by stable identity", () => {
    render(<ActivityTimeline navigate={vi.fn()} items={[item, item]} />);

    expect(screen.getAllByText("Check coverage")).toHaveLength(1);
  });

  it("reconstructs the same ordered activity identities across a reload", () => {
    const { rerender } = render(<ActivityTimeline navigate={vi.fn()} items={[item, second]} />);
    const first = renderedIds();

    // A reload re-delivers the same server page; a refetch may also re-deliver
    // an already-rendered item. Neither may change the rendered identities or
    // their order.
    rerender(<ActivityTimeline navigate={vi.fn()} items={[item, second]} />);
    expect(renderedIds()).toEqual(first);

    rerender(<ActivityTimeline navigate={vi.fn()} items={[item, second, second]} />);
    expect(renderedIds()).toEqual(first);
    expect(first).toEqual([item.activity_id, second.activity_id]);
  });

  it("renders the empty prompt without fabricating prior turns", () => {
    render(<ActivityTimeline navigate={vi.fn()} items={[]} />);

    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
    expect(screen.getByText(/Start a new conversation about this scenario/)).toBeInTheDocument();
  });

  it("renders supported evidence adjacent to its claim and failed claims distinctly", () => {
    render(<ActivityTimeline navigate={vi.fn()} items={[agentResponse]} />);

    expect(screen.getByLabelText("ShiftMind response")).toBeInTheDocument();
    const supported = screen.getByText("45 minutes").closest("[data-claim-state]");
    const evidence = screen.getByRole("button", {
      name: `Evidence: demand DEM-204, amount, 780–1020 minutes, fixture ${item.scenario_version_id}`,
    });
    expect(evidence).toHaveAttribute(
      "id",
      `evidence-origin-${agentResponse.activity_id}-1-0`,
    );
    expect(supported).toContainElement(evidence);
    expect(evidence.className).toContain("focus-visible:ring-3");
    expect(screen.getByText("Claim unavailable: version mismatch")).toHaveAttribute(
      "data-claim-state",
      "failed",
    );
    expect(screen.queryByText(/approximately|confidence|%/i)).not.toBeInTheDocument();
  });

  it("deduplicates an agent response delivered by SSE and timeline refetch", () => {
    render(<ActivityTimeline navigate={vi.fn()} items={[agentResponse, agentResponse]} />);
    expect(screen.getAllByLabelText("ShiftMind response")).toHaveLength(1);
    expect(screen.getAllByText(/45 minutes/)).toHaveLength(1);
  });

  it("names the task and window a number belongs to", () => {
    // The gate forbids numerals in prose and a claim carries no prose of its
    // own, so without this the answer is exact and unattributed at once.
    render(<ActivityTimeline navigate={vi.fn()} items={[agentResponse]} />);
    expect(screen.getByText(/pick · outbound · 780–1020 min/)).toBeInTheDocument();
  });

  it("drops float repr noise without truncating a real magnitude", () => {
    // Demand volume carries float amounts throughout the fixture, so
    // 90.00000000000001 is reachable in a feature whose premise is exactness.
    // A fixed 2-decimal form fixed that but created a worse failure: a genuine
    // 0.0001 rendered as "0.00" beside an Evidence link proving it is nonzero.
    const floaty = {
      ...agentResponse,
      response: {
        ...agentResponse.response,
        segments: [
          {
            ...agentResponse.response.segments[1],
            value: 90.00000000000001,
            unit: "units" as const,
          },
        ],
      },
    };
    render(<ActivityTimeline navigate={vi.fn()} items={[floaty]} />);

    expect(screen.getByText(/90 units/)).toBeInTheDocument();
    expect(screen.queryByText(/90\.00000000000001/)).not.toBeInTheDocument();
  });

  it("never renders a small nonzero value as zero", () => {
    const tiny = {
      ...agentResponse,
      response: {
        ...agentResponse.response,
        segments: [
          {
            ...agentResponse.response.segments[1],
            value: 0.0001,
            unit: "units" as const,
          },
        ],
      },
    };
    render(<ActivityTimeline navigate={vi.fn()} items={[tiny]} />);

    expect(screen.getByText(/0\.0001 units/)).toBeInTheDocument();
    expect(screen.queryByText(/^0 units/)).not.toBeInTheDocument();
  });

  it("renders a proven-empty match set as its own state, never a bare number", () => {
    // A calculator that legitimately matches nothing returns value 0 with NO
    // locator, because EvidenceRefV1 addresses records and absence has none.
    // Rendering that as "0" left a number with no adjacent Evidence link, which
    // AC2 forbids.
    const emptySet = {
      ...agentResponse,
      response: {
        ...agentResponse.response,
        segments: [
          {
            ...agentResponse.response.segments[1],
            value: 0,
            evidence_refs: [],
          },
        ],
      },
    };
    render(<ActivityTimeline navigate={vi.fn()} items={[emptySet]} />);

    expect(screen.getByText(/No matching records/)).toHaveAttribute(
      "data-claim-state",
      "empty",
    );
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("reports an empty response neutrally, without asserting the run failed", () => {
    // An empty segment list does NOT imply failure: `terminal_status` returns
    // `agent_completed` whenever a grounded response exists, so a model that
    // answers with zero segments completes successfully and renders here too.
    // The activity payload carries no run status, so claiming "did not
    // complete" in destructive styling was wrong for the completed case.
    // New failures use terminal_outcome; this branch remains for historical rows.
    const empty = {
      ...agentResponse,
      response: { ...agentResponse.response, segments: [] },
    };
    render(<ActivityTimeline navigate={vi.fn()} items={[empty]} />);

    expect(screen.getByText(/No answer was saved for this turn/)).toHaveAttribute(
      "data-response-state",
      "empty",
    );
  });

  it("renders a clarification with trusted candidates and dropped-count disclosure", () => {
    render(<ActivityTimeline navigate={vi.fn()} items={[clarification]} />);

    expect(screen.getByText("Clarification")).toBeInTheDocument();
    expect(screen.getByText("Which worker did you mean?")).toBeInTheDocument();
    expect(screen.getByText(/CONTACT-9/)).toHaveTextContent("workers");
    expect(screen.getByText(/1 candidate could not be resolved/)).toBeInTheDocument();
  });

  it("keeps the model's wording out of the application-resolved record list", () => {
    // The question names two people who do not exist. The resolved list is the
    // only part the application vouched for, so it must (a) be identifiable as
    // such, and (b) contain nothing the model wrote.
    const fabricated = ["Taylor Smith", "Jordan Lee"];
    const withFabricatedNames = {
      ...clarification,
      clarification: {
        ...clarification.clarification,
        question: `Did you mean ${fabricated[0]} or ${fabricated[1]}?`,
      },
    };

    render(<ActivityTimeline navigate={vi.fn()} items={[withFabricatedNames]} />);

    const records = screen.getByRole("list", { name: "Records in Scenario Data" });
    expect(records).toBeInTheDocument();
    expect(records.textContent).toContain("CONTACT-9");
    for (const name of fabricated) {
      // Present in the question, absent from the verified list.
      expect(screen.getByText(new RegExp(name))).toBeInTheDocument();
      expect(records.textContent).not.toContain(name);
    }
  });

  it("renders a refusal as a literal terminal outcome with its safe next step", () => {
    render(<ActivityTimeline navigate={vi.fn()} items={[refusal]} />);

    expect(screen.getByText("Refusal")).toBeInTheDocument();
    // The human label, not the raw enum. A planner should never be shown the
    // wire vocabulary, and `refusal_reason` is absent here so the shared
    // "Refusal" fallback is what renders.
    expect(screen.getByText(/Refusal: That capability is not available/)).toBeInTheDocument();
    expect(screen.getByText("Review Scenario Data.")).toBeInTheDocument();
  });

  it("renders every terminal reason with pairwise-distinct literal output", () => {
    const reasons = [
      "provider_error",
      "invalid_output",
      "budget_exhausted",
      "deadline_exceeded",
      "capability_error",
      "refused",
      "approval_not_grantable",
    ] as const;
    // `detail` is IDENTICAL across every reason on purpose. The previous form
    // interpolated the reason into the detail string and then asserted the
    // rendered strings differed — so the fixture supplied the distinctness and
    // the test would have passed even if `terminalLabel` collapsed all reasons
    // to one label. Holding detail constant means only the component's own
    // labelling can make these differ.
    const terminalItems = reasons.map((reason, index) => ({
      ...refusal,
      activity_id: `aaaaaaaa-aaaa-4aaa-8aaa-${String(index).padStart(12, "0")}`,
      sequence: String(index + 4),
      outcome: {
        ...refusal.outcome,
        status: reason === "refused" ? "completed" as const : "failed" as const,
        reason,
        detail: "the same detail for every reason",
      },
    }));

    render(<ActivityTimeline navigate={vi.fn()} items={terminalItems} />);

    const rendered = terminalItems.map(
      (item) =>
        document
          .querySelector(`[data-activity-id="${item.activity_id}"]`)
          ?.textContent ?? "",
    );
    expect(new Set(rendered).size).toBe(reasons.length);
  });

  it("labels the real approval-not-grantable reason, not the generic fallback", () => {
    // The pairwise-distinctness test above would still pass if this reason
    // fell through to the unmapped-reason fallback ("Turn ended") -- that
    // string is unique too, so it would never collide with the others. This
    // test pins the actual label so a missing `TERMINAL_LABELS` entry for a
    // real backend reason is caught here rather than passing silently.
    const notGrantable = {
      ...refusal,
      outcome: { ...refusal.outcome, status: "failed" as const, reason: "approval_not_grantable" as const },
    };

    render(<ActivityTimeline navigate={vi.fn()} items={[notGrantable]} />);

    expect(screen.getByText("Approval not available")).toBeInTheDocument();
    expect(screen.queryByText(/Turn ended/)).not.toBeInTheDocument();
  });

  it("labels a refusal by its model-selected reason, not one shared label", () => {
    const refusalReasons = [
      "unsupported_request",
      "capability_unavailable",
      "out_of_scope",
    ] as const;
    const items = refusalReasons.map((refusal_reason, index) => ({
      ...refusal,
      activity_id: `bbbbbbbb-bbbb-4bbb-8bbb-${String(index).padStart(12, "0")}`,
      sequence: String(index + 20),
      outcome: {
        ...refusal.outcome,
        status: "completed" as const,
        reason: "refused" as const,
        refusal_reason,
        detail: "the same detail for every reason",
      },
    }));

    render(<ActivityTimeline navigate={vi.fn()} items={items} />);

    expect(screen.getByText("Not supported")).toBeInTheDocument();
    expect(screen.getByText("Capability unavailable")).toBeInTheDocument();
    expect(screen.getByText("Out of scope")).toBeInTheDocument();
  });

  it("renders an unknown activity type without unmounting the timeline", () => {
    const unknown = {
      ...refusal,
      activity_id: "cccccccc-cccc-4ccc-8ccc-000000000000",
      activity_type: "run_progress",
    } as unknown as typeof item;

    render(<ActivityTimeline navigate={vi.fn()} items={[item, unknown]} />);

    // The known row survives — an unhandled discriminant must cost one row, not
    // the whole conversation.
    expect(screen.getByText(item.text)).toBeInTheDocument();
    expect(screen.getByText(/needs a newer version/i)).toBeInTheDocument();
  });
});
