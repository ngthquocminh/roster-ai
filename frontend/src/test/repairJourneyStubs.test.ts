import { describe, expect, it } from "vitest";

import {
  createRepairJourneyStubState,
  TERMINAL_RUN_IDS,
  TIMED_OUT_RUN_ID,
} from "../../e2e/support/repairJourneyStubState";

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
      state.completeRun();
      const terminalResult = state.nextResult();
      const laterResult = state.nextResult();
      return { beforeMessage, afterMessage, firstResult, reconnectResult, terminalResult, laterResult };
    };

    const first = exercise();
    const second = exercise();

    expect(first).toEqual(second);
    expect(first.beforeMessage).toHaveLength(1);
    // The planner's own message must persist alongside the draft, matching the
    // timeline the real `finalize_agent_run` path appends to.
    expect(first.afterMessage).toHaveLength(3);
    expect(first.afterMessage[1]).toMatchObject({
      activity_type: "planner_message",
      text: "Create a reversible repair draft.",
    });
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

  it("keeps the running state across any number of reads until the test advances it", () => {
    // Decision 4a asks for a TEST-controlled progression. Under the previous
    // call-counted model the third read flipped the run terminal on its own, so
    // one extra refetch (window focus, a remount, an added assertion) broke the
    // reconnect step. Reads must now be free of side effects.
    const state = createRepairJourneyStubState();
    state.acceptMessage();

    for (let read = 0; read < 12; read += 1) {
      expect(state.nextResult().run.status).toBe("solver_running");
    }

    state.completeRun();
    expect(state.nextResult().run.status).toBe("solver_completed");
    expect(state.nextResult().run.status).toBe("solver_completed");
  });

  it("serves a result for every terminal row it advertises in the runs table", () => {
    const state = createRepairJourneyStubState();
    const advertised = state.runPage().items.map((item) => item.schedule_run_id);

    // A row offering "View results" whose result endpoint 404s renders the
    // connection error, not TerminalOutcomeCard — the gap AC1 was missing.
    for (const runId of TERMINAL_RUN_IDS) {
      expect(advertised).toContain(runId);
      expect(state.terminalResult(runId)).toBeDefined();
    }
    expect(state.terminalResult("not-a-run")).toBeUndefined();
  });

  it("serves the timed-out run with its literal reason and no candidate evidence", () => {
    const state = createRepairJourneyStubState();
    const result = state.terminalResult(TIMED_OUT_RUN_ID);

    expect(result?.run.status).toBe("solver_timed_out");
    expect(result?.run.reason).toBe("Solver ceiling reached");
    expect(result?.candidate).toBeNull();
    expect(result?.comparison).toBeNull();
  });
});
