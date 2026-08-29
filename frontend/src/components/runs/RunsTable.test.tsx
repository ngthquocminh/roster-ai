import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

import * as cancelHooks from "@/hooks/useCancelScheduleRun";
import * as proposalsApi from "@/api/proposals";
import * as startHooks from "@/hooks/useStartScheduleRun";
import type { ScheduleRunSummary } from "@/api/scheduleRuns";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { RunsTable } from "./RunsTable";

vi.mock("@/hooks/useCancelScheduleRun");
vi.mock("@/api/proposals");
vi.mock("@/hooks/useStartScheduleRun");

const mutateCancel = vi.fn();
const mutateStart = vi.fn();
const SCENARIO_ID = "scenario-1";

function run(overrides: Partial<ScheduleRunSummary> = {}): ScheduleRunSummary {
  return {
    schedule_run_id: "11111111-1111-1111-1111-111111111111",
    status: "solver_completed",
    reason: null,
    resource_version: 2,
    created_at: "2026-08-22T10:00:00Z",
    updated_at: "2026-08-22T10:05:00Z",
    finished_at: "2026-08-22T10:05:00Z",
    scenario_version_id: "22222222-2222-2222-2222-222222222222",
    proposal_id: "33333333-3333-3333-3333-333333333333",
    proposal_version: 5,
    baseline_schedule_version: null,
    ...overrides,
  };
}

function renderTable(runs: ScheduleRunSummary[], props: Partial<React.ComponentProps<typeof RunsTable>> = {}) {
  // Retry reads the proposal on click via `queryClient.fetchQuery`, so the
  // table needs a real client. `retry: false` keeps a rejected read from
  // being re-attempted behind the assertion.
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <RunsTable error={null} isLoading={false} runs={runs} scenarioId={SCENARIO_ID} {...props} />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(cancelHooks.useCancelScheduleRun).mockReturnValue({
    mutate: mutateCancel,
    isPending: false,
    isError: false,
    error: null,
  } as never);
  vi.mocked(proposalsApi.getProposal).mockResolvedValue({
    resource_version: 9,
  } as never);
  vi.mocked(startHooks.useStartScheduleRun).mockReturnValue({
    mutate: mutateStart,
    isPending: false,
    isSuccess: false,
    isError: false,
    error: null,
  } as never);
});

describe("RunsTable", () => {
  it("shows a loading state without rendering rows", () => {
    renderTable([], { isLoading: true, runs: [] });
    expect(screen.getByRole("status", { name: "Loading runs" })).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("shows the shared alert state on list failure without hiding the page", () => {
    renderTable([], { error: new Error("boom"), runs: [] });
    expect(screen.getByText("Couldn't load this content.")).toBeInTheDocument();
  });

  it("offers a retry action on list failure when the caller supplies one", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    renderTable([], { error: new Error("boom"), runs: [], onRetry });
    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("shows an empty state for no runs", () => {
    renderTable([]);
    expect(screen.getByText(/no runs yet/i)).toBeInTheDocument();
  });

  it("renders rows in the given order (newest-first is the caller's contract)", () => {
    const first = run({ schedule_run_id: "run-a" });
    const second = run({ schedule_run_id: "run-b" });
    renderTable([first, second]);
    const rows = screen.getAllByRole("row").slice(1); // drop header row
    expect(within(rows[0]).getByText("run-a")).toBeInTheDocument();
    expect(within(rows[1]).getByText("run-b")).toBeInTheDocument();
  });

  it("reads status verbatim from the run record, never recomputed (Trap 7)", () => {
    renderTable([run({ status: "solver_infeasible" })]);
    expect(screen.getByLabelText("Infeasible")).toBeInTheDocument();
  });

  it("renders baseline as an em dash when null, never empty or zero (Trap 4)", () => {
    renderTable([run({ baseline_schedule_version: null })]);
    const row = screen.getAllByRole("row")[1];
    expect(within(row).getByText("—")).toBeInTheDocument();
  });

  it.each(["solver_queued", "solver_running"] as const)(
    "shows Cancel for non-terminal %s",
    (status) => {
      renderTable([run({ status })]);
      expect(screen.getByRole("button", { name: "Cancel" })).toBeInTheDocument();
    },
  );

  it.each([
    "cancellation_requested",
    "solver_completed",
    "solver_infeasible",
    "solver_timed_out",
    "solver_cancelled",
    "solver_failed",
  ] as const)("does not show Cancel for %s", (status) => {
    renderTable([run({ status })]);
    expect(screen.queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("calls the cancel mutation with the run's resource_version, not a client guess (Trap 5)", async () => {
    const user = userEvent.setup();
    renderTable([run({ status: "solver_running", resource_version: 7 })]);
    await user.click(screen.getByRole("button", { name: "Cancel" }));
    expect(mutateCancel).toHaveBeenCalledWith({ expected_resource_version: 7 });
  });

  it.each([
    "solver_completed",
    "solver_infeasible",
    "solver_timed_out",
    "solver_cancelled",
    "solver_failed",
  ] as const)("shows Retry for terminal %s", (status) => {
    renderTable([run({ status })]);
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  });

  it.each(["solver_queued", "solver_running", "cancellation_requested"] as const)(
    "does not show Retry for non-terminal %s",
    (status) => {
      renderTable([run({ status })]);
      expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    },
  );

  it("retries with the proposal's CURRENT resource_version, not this run's historical one (Trap 3)", async () => {
    const user = userEvent.setup();
    renderTable([run({ status: "solver_completed", proposal_id: "proposal-9" })]);
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(mutateStart).toHaveBeenCalledWith({
        proposal_id: "proposal-9",
        expected_resource_version: 9, // the live proposal read, not run.resource_version (2)
      }),
    );
    expect(proposalsApi.getProposal).toHaveBeenCalledWith("proposal-9");
  });

  it("reads the proposal only when Retry is pressed, never once per row on mount", () => {
    // One `useProposal` per retryable row fired a full page of proposal reads
    // on first paint purely to decide whether to enable a button.
    renderTable([
      run({ schedule_run_id: "run-a", proposal_id: "proposal-a" }),
      run({ schedule_run_id: "run-b", proposal_id: "proposal-b" }),
      run({ schedule_run_id: "run-c", proposal_id: "proposal-c" }),
    ]);
    expect(proposalsApi.getProposal).not.toHaveBeenCalled();
    for (const button of screen.getAllByRole("button", { name: "Retry" })) {
      expect(button).toBeEnabled();
    }
  });

  it("keeps Retry pressable after a failed proposal read, and reports the failure", async () => {
    // The old gate (`disabled = !proposal.data`) left Retry permanently inert
    // after one transient read failure -- the speculative disable the
    // guardrails argue against.
    const user = userEvent.setup();
    vi.mocked(proposalsApi.getProposal).mockRejectedValueOnce({ status: 503 });
    renderTable([run({ status: "solver_completed", proposal_id: "proposal-9" })]);

    await user.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByText(/could not be read/)).toBeInTheDocument();
    expect(mutateStart).not.toHaveBeenCalled();

    const retry = screen.getByRole("button", { name: "Retry" });
    expect(retry).toBeEnabled();
    await user.click(retry);
    await waitFor(() => expect(mutateStart).toHaveBeenCalledTimes(1));
  });

  it("does not create a new retry route -- reuses the existing start-run mutation hook", async () => {
    const user = userEvent.setup();
    renderTable([run({ status: "solver_completed" })]);
    expect(startHooks.useStartScheduleRun).toHaveBeenCalled();
    await user.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(mutateStart).toHaveBeenCalled());
  });

  it("shows View progress for non-terminal runs and View results for terminal ones", () => {
    renderTable([run({ status: "solver_running" })]);
    expect(screen.getByRole("link", { name: "View progress" })).toHaveAttribute(
      "href",
      `/scenarios/${SCENARIO_ID}/runs/${run().schedule_run_id}`,
    );
    vi.clearAllMocks();
    renderTable([run({ status: "solver_completed" })]);
    expect(screen.getByRole("link", { name: "View results" })).toBeInTheDocument();
  });

  it("shows no view link for solver_cancelled (no candidate to view)", () => {
    renderTable([run({ status: "solver_cancelled" })]);
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("links completed runs to the reviewed approval surface", () => {
    renderTable([run({ status: "solver_completed" })]);
    expect(screen.getByRole("link", { name: "Review for approval" })).toHaveAttribute(
      "href", "/scenarios/scenario-1/runs/11111111-1111-1111-1111-111111111111",
    );
  });

  it("provides a separate, labelled copy control for the run id", () => {
    renderTable([run()]);
    expect(screen.getByRole("button", { name: /Copy Run ID/ })).toBeInTheDocument();
  });
});

it("shows an updated time for a non-terminal run, which has no finish time", () => {
  // AC1 asks for an "updated time". The column used to render `finished_at`,
  // which is null for exactly the runs a planner opens this table to monitor,
  // so every in-flight row showed a permanent em dash.
  renderTable([
    run({
      status: "solver_running",
      finished_at: null,
      updated_at: "2026-08-22T11:30:00Z",
      created_at: "2026-08-22T10:00:00Z",
    }),
  ]);

  // The Baseline column legitimately renders "—" (Trap 4), so assert on the
  // Updated cell itself rather than on the absence of an em dash anywhere.
  expect(
    screen.getByRole("cell", { name: formatTimestamp("2026-08-22T11:30:00Z") }),
  ).toBeInTheDocument();
});
