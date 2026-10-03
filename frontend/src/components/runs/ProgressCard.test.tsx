import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ProgressCard } from "./ProgressCard";
import type { ScheduleRunSummary } from "@/api/scheduleRuns";

const FORBIDDEN = [/%/, /eta/i, /remaining/i, /likely/i, /probably/i];

function run(overrides: Partial<ScheduleRunSummary> = {}): ScheduleRunSummary {
  return {
    schedule_run_id: "11111111-1111-1111-1111-111111111111",
    status: "solver_running",
    reason: null,
    resource_version: 1,
    created_at: "2026-08-22T10:00:00Z",
    updated_at: "2026-08-22T10:03:00Z",
    finished_at: null,
    scenario_version_id: "22222222-2222-2222-2222-222222222222",
    proposal_id: "33333333-3333-3333-3333-333333333333",
    proposal_version: 1,
    baseline_schedule_version: null,
    ...overrides,
  };
}

describe.each(["solver_queued", "solver_running", "cancellation_requested"] as const)(
  "ProgressCard for %s",
  (status) => {
    it("renders literal status and timestamp with no forbidden token", () => {
      const { container } = render(<ProgressCard run={run({ status })} />);
      const text = container.textContent ?? "";
      expect(text).toContain("2026-08-22 10:00");
      for (const pattern of FORBIDDEN) expect(text).not.toMatch(pattern);
    });

    it("renders no progressbar or spinner element", () => {
      render(<ProgressCard run={run({ status })} />);
      expect(screen.queryByRole("progressbar")).not.toBeInTheDocument();
    });
  },
);

it("renders 'Accepted time not recorded' rather than a formatted null timestamp", () => {
  render(<ProgressCard run={{ status: "solver_running", created_at: null }} />);
  expect(screen.getByText("Accepted time not recorded")).toBeInTheDocument();
});
