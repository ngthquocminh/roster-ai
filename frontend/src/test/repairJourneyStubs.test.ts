import { describe, expect, it } from "vitest";

import { createRepairJourneyStubState } from "../../e2e/support/repairJourneyStubState";

describe("repair journey API stub state", () => {
  it("replays the same message and result progression for every fresh instance", () => {
    const exercise = () => {
      const state = createRepairJourneyStubState();
      const existingClaim = { activity_type: "agent_response", activity_id: "claim-1" };
      const beforeMessage = state.timelineItems([existingClaim]);
      state.acceptMessage();
      const afterMessage = state.timelineItems([existingClaim]);
      const firstResult = state.nextResult();
      const reconnectResult = state.nextResult();
      const terminalResult = state.nextResult();
      const laterResult = state.nextResult();
      return { beforeMessage, afterMessage, firstResult, reconnectResult, terminalResult, laterResult };
    };

    const first = exercise();
    const second = exercise();

    expect(first).toEqual(second);
    expect(first.beforeMessage).toHaveLength(1);
    expect(first.afterMessage).toHaveLength(2);
    expect(first.afterMessage.at(-1)).toMatchObject({
      activity_type: "draft",
      consequence_summary: "One reversible repair constraint; no baseline change.",
    });
    expect(first.firstResult.run.status).toBe("solver_running");
    expect(first.firstResult.candidate).toBeNull();
    expect(first.reconnectResult).toEqual(first.firstResult);
    expect(first.terminalResult.run.status).toBe("solver_completed");
    expect(first.terminalResult.candidate?.assignments).not.toHaveLength(0);
    expect(first.terminalResult.comparison?.evidence_refs).not.toHaveLength(0);
    expect(first.laterResult).toEqual(first.terminalResult);
  });
});
