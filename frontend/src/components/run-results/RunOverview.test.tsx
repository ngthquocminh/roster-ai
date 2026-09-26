import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { describe, expect, it, vi } from "vitest";

import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { RunOverview } from "./RunOverview";

type Candidate = NonNullable<ScheduleRunResult["candidate"]>;

function candidate(overrides: Partial<Candidate["metrics"]> = {}): Candidate {
  return {
    schedule_version_id: "cand-1",
    schedule_run_id: "run-1",
    assignments: [{ record_id: "a1", worker_id: "W1", task_id: "T1", shift_id: null, start_minute: 0, end_minute: 480 }],
    metrics: {
      interval_coverage_required_minutes: [["demand-1", 60], ["demand-2", 60]],
      interval_coverage_served_minutes: [["demand-1", 45], ["demand-2", 60]],
      function_coverage_required_minutes: [["Picking", 120]],
      function_coverage_served_minutes: [["Picking", 105]],
      overtime_minutes: 30, total_cost: 125, objective_components: [], assignment_count: 1, member_count: 1, schema_version: "1",
      ...overrides,
    },
  } as Candidate;
}

function props(extra: Partial<Parameters<typeof RunOverview>[0]> = {}) {
  return {
    candidate: candidate(), candidateVersionId: "cand-1", baselineVersion: "baseline-v1", stale: false,
    onRequestApproval: vi.fn(), requestPending: false, requestError: false, pendingApproval: false, ...extra,
  };
}

const gapSummary = (re: RegExp) => screen.getByText((_, el) => el?.tagName === "P" && re.test(el.textContent ?? ""));

describe("RunOverview", () => {
  it("summarises coverage, gaps and charts instead of listing every gap", () => {
    render(<RunOverview {...props()} />);
    expect(screen.getByText("87.5%")).toBeInTheDocument();
    expect(gapSummary(/1 of 2 demand intervals/)).toBeInTheDocument();
    const list = screen.getByRole("list", { name: "Coverage by function" });
    expect(within(list).getByText("Picking")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: "Scheduled hours by day" })).toHaveTextContent("8.0 h");
    expect(within(screen.getByRole("list", { name: "Largest gaps" })).getAllByRole("listitem")).toHaveLength(1);
  });

  it("caps the largest-gaps list at five for many gaps", () => {
    const ids = Array.from({ length: 300 }, (_, i) => `d-${i}`);
    render(<RunOverview {...props({ candidate: candidate({
      interval_coverage_required_minutes: ids.map((id) => [id, 60]),
      interval_coverage_served_minutes: [],
    }) })} />);
    expect(within(screen.getByRole("list", { name: "Largest gaps" })).getAllByRole("listitem")).toHaveLength(5);
    expect(gapSummary(/300 of 300 demand intervals/)).toBeInTheDocument();
  });

  it("says so when there are no gaps and shows a dash for zero demand", () => {
    render(<RunOverview {...props({ candidate: candidate({ interval_coverage_required_minutes: [], interval_coverage_served_minutes: [], function_coverage_required_minutes: [], function_coverage_served_minutes: [] }) })} />);
    expect(screen.getByText(/No unresolved gaps/)).toBeInTheDocument();
    expect(screen.getByText("Coverage").nextElementSibling).toHaveTextContent("—");
  });

  it("disables the request when pending-state is unknown, and says why", () => {
    render(<RunOverview {...props({ pendingApproval: true, approvalsUnavailable: true })} />);
    expect(screen.getByRole("button", { name: "Request approval" })).toBeDisabled();
    expect(screen.getByText(/Existing approvals couldn't be loaded/)).toBeInTheDocument();
    expect(screen.queryByText("A decision is already pending.")).not.toBeInTheDocument();
  });

  it("calls onRequestApproval when enabled", async () => {
    const p = props();
    render(<RunOverview {...p} />);
    await userEvent.click(screen.getByRole("button", { name: "Request approval" }));
    expect(p.onRequestApproval).toHaveBeenCalledTimes(1);
  });

  it.each([
    ["stale", { stale: true }, "Comparison is stale — refresh before requesting approval."],
    ["pending", { pendingApproval: true }, "A decision is already pending."],
  ])("disables the control with a visible reason when %s", (_name, extra, text) => {
    render(<RunOverview {...props(extra)} />);
    expect(screen.getByRole("button", { name: "Request approval" })).toBeDisabled();
    expect(screen.getByText(text)).toBeInTheDocument();
  });

  it("disables while in flight and surfaces a request failure", () => {
    render(<RunOverview {...props({ requestPending: true, requestError: true })} />);
    expect(screen.getByRole("button", { name: "Request approval" })).toBeDisabled();
    expect(screen.getByText("Approval request not created")).toBeInTheDocument();
  });

  it("meets the automated accessibility floor", async () => {
    const { container } = render(<RunOverview {...props()} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
