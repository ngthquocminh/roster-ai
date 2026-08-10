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
});
