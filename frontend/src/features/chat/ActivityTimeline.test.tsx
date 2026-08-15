import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

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

function renderedIds() {
  return screen
    .getAllByRole("listitem")
    .map((node) => node.getAttribute("data-activity-id"));
}

describe("ActivityTimeline", () => {
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
    render(<ActivityTimeline items={[agentResponse]} />);

    expect(screen.getByText("45 minutes")).toBeInTheDocument();
    expect(screen.getByText("Evidence unavailable")).toBeInTheDocument();
  });
  it("deduplicates replayed activity by stable identity", () => {
    render(<ActivityTimeline items={[item, item]} />);

    expect(screen.getAllByText("Check coverage")).toHaveLength(1);
  });

  it("reconstructs the same ordered activity identities across a reload", () => {
    const { rerender } = render(<ActivityTimeline items={[item, second]} />);
    const first = renderedIds();

    // A reload re-delivers the same server page; a refetch may also re-deliver
    // an already-rendered item. Neither may change the rendered identities or
    // their order.
    rerender(<ActivityTimeline items={[item, second]} />);
    expect(renderedIds()).toEqual(first);

    rerender(<ActivityTimeline items={[item, second, second]} />);
    expect(renderedIds()).toEqual(first);
    expect(first).toEqual([item.activity_id, second.activity_id]);
  });

  it("renders the empty prompt without fabricating prior turns", () => {
    render(<ActivityTimeline items={[]} />);

    expect(screen.queryByRole("listitem")).not.toBeInTheDocument();
    expect(screen.getByText(/Start a new conversation about this scenario/)).toBeInTheDocument();
  });

  it("renders supported evidence adjacent to its claim and failed claims distinctly", () => {
    render(<ActivityTimeline items={[agentResponse]} />);

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
    expect(document.body.innerHTML).not.toMatch(/gradient|animate-pulse|ai-glow/i);
  });

  it("deduplicates an agent response delivered by SSE and timeline refetch", () => {
    render(<ActivityTimeline items={[agentResponse, agentResponse]} />);
    expect(screen.getAllByLabelText("ShiftMind response")).toHaveLength(1);
    expect(screen.getAllByText(/45 minutes/)).toHaveLength(1);
  });

  it("names the task and window a number belongs to", () => {
    // The gate forbids numerals in prose and a claim carries no prose of its
    // own, so without this the answer is exact and unattributed at once.
    render(<ActivityTimeline items={[agentResponse]} />);
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
    render(<ActivityTimeline items={[floaty]} />);

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
    render(<ActivityTimeline items={[tiny]} />);

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
    render(<ActivityTimeline items={[emptySet]} />);

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
    // Story 2.9 owns the taxonomy that can tell them apart.
    const empty = {
      ...agentResponse,
      response: { ...agentResponse.response, segments: [] },
    };
    render(<ActivityTimeline items={[empty]} />);

    expect(screen.getByText(/No answer was saved for this turn/)).toHaveAttribute(
      "data-response-state",
      "empty",
    );
  });
});
