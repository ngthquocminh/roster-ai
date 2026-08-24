import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { describe, expect, it } from "vitest";

import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { ComparisonSummary } from "./ComparisonSummary";

function comparison(stale = false): NonNullable<ScheduleRunResult["comparison"]> {
  const metrics = {
    interval_coverage_required_minutes: [["demand-1", 60]],
    interval_coverage_served_minutes: [["demand-1", 45]],
    function_coverage_required_minutes: [["Picking", 60]],
    function_coverage_served_minutes: [["Picking", 45]],
    overtime_minutes: 10,
    total_cost: 125,
    objective_components: [["unmet_minutes", 15]],
    assignment_count: 1,
    member_count: 1,
    schema_version: "1",
  };
  return {
    candidate_schedule_version_id: "11111111-1111-1111-1111-111111111111",
    candidate_schedule_run_id: "22222222-2222-2222-2222-222222222222",
    scenario_id: "33333333-3333-3333-3333-333333333333",
    scenario_version_id: "44444444-4444-4444-4444-444444444444",
    expected_baseline_schedule_version: "baseline-v1",
    current_baseline_schedule_version: stale ? "baseline-v2" : "baseline-v1",
    stale,
    assignment_diff: {
      added_worker_ids: ["worker-1"], removed_worker_ids: ["worker-2"],
      added_shift_ids: ["shift-1"], removed_shift_ids: [],
      added_task_ids: ["task-1"], removed_task_ids: [], schema_version: "1",
    },
    candidate_metrics: metrics,
    baseline_metrics: { ...metrics, interval_coverage_served_minutes: [], overtime_minutes: 0, total_cost: 100, objective_components: [["unmet_minutes", 60]], assignment_count: 0, member_count: 0 },
    candidate_constraint_results: [{ constraint_id: "hard:q", constraint_type: "qualification", constraint_class: "hard", satisfied: true, measured_value: 0, limit: 0, unit: "assignments", contributing_assignment_ids: [], contributing_evidence_refs: [], schema_version: "1" }],
    baseline_hard_constraint_results: [],
    warnings: ["Review overtime"],
    unresolved_gap_record_ids: ["demand-1"],
    evidence_refs: [],
    schema_version: "1",
  } as NonNullable<ScheduleRunResult["comparison"]>;
}

describe("ComparisonSummary", () => {
  it("renders all decision fields, genuine absence, and a disabled approval", () => {
    render(<ComparisonSummary comparison={comparison()} />);
    expect(screen.getByText("worker-1")).toBeInTheDocument();
    expect(screen.getByText(/Cost delta/)).toBeInTheDocument();
    expect(screen.getByText(/Overtime delta/)).toBeInTheDocument();
    expect(screen.getByText("Review overtime")).toBeInTheDocument();
    expect(screen.getByText("demand-1")).toBeInTheDocument();
    expect(screen.getAllByText("Not computed").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Approve as baseline" })).toBeDisabled();
  });

  it("renders a real zero coverage delta for genuinely zero demand, not 'Not computed'", () => {
    // Both sides empty is what a scenario with zero demand rows produces --
    // calculate_candidate_metrics always populates this field, so an empty
    // tuple here is a real answer (0), never an absent one (Trap 6).
    const zeroDemand = comparison();
    zeroDemand.candidate_metrics = {
      ...zeroDemand.candidate_metrics,
      interval_coverage_required_minutes: [],
      interval_coverage_served_minutes: [],
    };
    zeroDemand.baseline_metrics = {
      ...zeroDemand.baseline_metrics,
      interval_coverage_required_minutes: [],
      interval_coverage_served_minutes: [],
    };

    render(<ComparisonSummary comparison={zeroDemand} />);

    expect(screen.getByText(/Coverage required delta/).nextElementSibling).toHaveTextContent("0.00");
    expect(screen.getByText(/Coverage served delta/).nextElementSibling).toHaveTextContent("0.00");
  });

  it("keeps historical numbers visible under the stale warning", () => {
    render(<ComparisonSummary comparison={comparison(true)} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/baseline-v1.*baseline-v2/i);
    expect(screen.getByText(/Cost delta/)).toBeInTheDocument();
  });

  it("meets the automated accessibility floor", async () => {
    const { container } = render(<ComparisonSummary comparison={comparison(true)} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
