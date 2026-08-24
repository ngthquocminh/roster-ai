import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { TerminalOutcomeCard } from "./TerminalOutcomeCard";

const statuses = [
  "solver_queued", "solver_running", "cancellation_requested",
  "solver_infeasible", "solver_timed_out", "solver_cancelled", "solver_failed",
] as const;

describe("TerminalOutcomeCard", () => {
  for (const status of statuses) {
    it(`renders ${status} literally without speculative or approval copy`, () => {
      const run = {
        schedule_run_id: "11111111-1111-1111-1111-111111111111",
        status,
        reason: "literal_reason",
        resource_version: 2,
        cancellation_requested: status === "cancellation_requested",
        created_at: null,
        finished_at: null,
      } satisfies ScheduleRunResult["run"];
      render(<TerminalOutcomeCard run={run} />);

      expect(screen.getByText("literal_reason")).toBeInTheDocument();
      expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
      expect(document.body.textContent).not.toMatch(/%|ETA|remaining|likely|probably/i);
    });
  }

  it("meets the automated accessibility floor", async () => {
    const { container } = render(<TerminalOutcomeCard run={{
      schedule_run_id: "11111111-1111-1111-1111-111111111111",
      status: "solver_failed", reason: "model_invalid", resource_version: 2,
      cancellation_requested: false, created_at: null, finished_at: null,
    }} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
