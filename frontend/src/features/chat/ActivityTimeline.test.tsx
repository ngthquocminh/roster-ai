import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ActivityTimeline } from "./ActivityTimeline";

const item = { schema_version: "1", activity_id: "11111111-1111-1111-1111-111111111111", activity_type: "planner_message" as const, conversation_id: "22222222-2222-2222-2222-222222222222", conversation_resource_version: 2, scenario_id: "33333333-3333-3333-3333-333333333333", scenario_version_id: "44444444-4444-4444-4444-444444444444", occurred_at: "2026-08-10T00:00:00Z", message_id: "55555555-5555-5555-5555-555555555555", text: "Check coverage" };

describe("ActivityTimeline", () => {
  it("deduplicates replayed activity by stable identity", () => { render(<ActivityTimeline items={[item, item]} />); expect(screen.getAllByText("Check coverage")).toHaveLength(1); });
  it("preserves the server's ordered activity identities on reconstruction", () => { const second = { ...item, activity_id: "66666666-6666-6666-6666-666666666666", message_id: "77777777-7777-7777-7777-777777777777", text: "Then constraints" }; render(<ActivityTimeline items={[item, second]} />); expect(screen.getAllByRole("listitem").map((node) => node.textContent)).toEqual(["Check coverage", "Then constraints"]); });
});
