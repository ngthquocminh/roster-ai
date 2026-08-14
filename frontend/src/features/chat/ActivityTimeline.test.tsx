import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ActivityTimeline } from "./ActivityTimeline";

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
        metric: "shortfall_minutes" as const,
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

  it("rounds a float value rather than showing its raw repr", () => {
    // Demand volume carries float amounts throughout the fixture, so
    // 90.00000000000001 is reachable in a feature whose premise is exactness.
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

    expect(screen.getByText(/90\.00 units/)).toBeInTheDocument();
    expect(screen.queryByText(/90\.00000000000001/)).not.toBeInTheDocument();
  });

  it("renders a failed run's empty response as a named state, not a blank bubble", () => {
    // A failed or timed-out run persists a response with no segments. That is
    // truthful, but an empty bubble under the ShiftMind label reads as the
    // assistant having said nothing at all.
    const empty = {
      ...agentResponse,
      response: { ...agentResponse.response, segments: [] },
    };
    render(<ActivityTimeline items={[empty]} />);

    expect(screen.getByText(/This turn did not complete/)).toHaveAttribute(
      "data-response-state",
      "unavailable",
    );
  });
});
