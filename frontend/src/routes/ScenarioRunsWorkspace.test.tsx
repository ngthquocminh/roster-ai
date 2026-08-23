import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

/**
 * The one place the Runs workspace is exercised with its REAL parts wired
 * together: `ScenarioWorkspace`, `WorkspaceTabs`, `ScenarioRuns`, `RunsTable`,
 * `useScheduleRuns`, `useStartScheduleRun`, `useCancelScheduleRun` and a real
 * `QueryClient`. Only the network seam is mocked.
 *
 * Every other test in this story mocks either the table (`ScenarioRuns.test`)
 * or all three hooks (`RunsTable.test`), which is why a Retry that queued a run
 * without ever refreshing the list passed a fully green suite. A component and
 * its hook can each be correct while the wire between them is not.
 *
 * It also carries AC2's last clause — "manual deterministic Run optimization
 * remains available when permitted" — read at the APPLICATION level (code
 * review 2026-08-23, Decision 3). "Remains" preserves a capability that
 * already exists: the Run optimization control is Story 3.6's and lives in
 * Chat. The failure mode that would break the clause is a Runs route that
 * early-returns over the workspace shell on a list failure, taking the tab bar
 * with it — so what is proved here is that the shell survives.
 */
vi.mock("@/hooks/useScenarioContext", () => ({
  useScenarioContext: vi.fn(),
}));
vi.mock("@/api/scheduleRuns");
vi.mock("@/api/proposals");

import { getProposal } from "@/api/proposals";
import { listScheduleRuns, startScheduleRun } from "@/api/scheduleRuns";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { ScenarioRuns } from "./ScenarioRuns";
import { ScenarioWorkspace } from "./ScenarioWorkspace";

const mockContext = vi.mocked(useScenarioContext);
const mockList = vi.mocked(listScheduleRuns);
const mockStart = vi.mocked(startScheduleRun);
const mockProposal = vi.mocked(getProposal);

const scenarioId = "11111111-1111-4111-8111-111111111111";
const runId = "44444444-4444-4444-8444-444444444444";
const proposalId = "33333333-3333-4333-8333-333333333333";

const context = {
  schema_version: "v1",
  scenario_name: "Fixture A",
  scenario_id: scenarioId,
  fixture_version: "v1",
  checksum_algorithm: "sha256",
  checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64),
  site_id: "22222222-2222-4222-8222-222222222222",
  baseline_schedule_version: null,
};

function page(overrides: Record<string, unknown> = {}) {
  return {
    scenario_id: scenarioId,
    items: [
      {
        schedule_run_id: runId,
        status: "solver_completed",
        reason: null,
        resource_version: 2,
        created_at: "2026-08-22T10:00:00Z",
        updated_at: "2026-08-22T10:05:00Z",
        finished_at: "2026-08-22T10:05:00Z",
        scenario_version_id: "55555555-5555-4555-8555-555555555555",
        proposal_id: proposalId,
        proposal_version: 5,
        baseline_schedule_version: null,
      },
    ],
    next_cursor: null,
    total_count: 1,
    matching_count: 1,
    ...overrides,
  };
}

function renderRunsTab() {
  const router = createMemoryRouter(
    [
      {
        path: "/scenarios/:scenarioId",
        Component: ScenarioWorkspace,
        children: [{ path: "runs", Component: ScenarioRuns }],
      },
      { path: "/signin", element: <p>Sign in surface</p> },
      { path: "/", element: <p>Catalogue surface</p> },
    ],
    { initialEntries: [`/scenarios/${scenarioId}/runs`] },
  );
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return queryClient;
}

beforeEach(() => {
  vi.clearAllMocks();
  mockContext.mockReturnValue({
    data: context,
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  } as never);
});

it("renders a real run row end to end, from the API payload through the real hook", async () => {
  mockList.mockResolvedValue(page() as never);

  renderRunsTab();

  expect(await screen.findByRole("button", { name: `Copy Run ID ${runId}` })).toBeInTheDocument();
  expect(screen.getByText("Completed")).toBeInTheDocument();
  expect(mockList).toHaveBeenCalledWith({ scenario_id: scenarioId, cursor: 0 });
});

it("re-reads the list after Retry queues a run, so the new run can appear", async () => {
  const user = userEvent.setup();
  mockList.mockResolvedValue(page() as never);
  mockProposal.mockResolvedValue({ resource_version: 9 } as never);
  mockStart.mockResolvedValue({
    schedule_run_id: "66666666-6666-4666-8666-666666666666",
    status: "solver_queued",
    reason: null,
    resource_version: 1,
    cancellation_requested: false,
  } as never);

  renderRunsTab();
  await screen.findByText("Completed");
  expect(mockList).toHaveBeenCalledTimes(1);

  await user.click(screen.getByRole("button", { name: "Retry" }));

  await waitFor(() => expect(mockStart).toHaveBeenCalled());
  // The whole point: the started run is a new row, so the list must be
  // re-read. Without the invalidation this stayed at one call and the planner
  // saw "queued" over an unchanged table.
  await waitFor(() => expect(mockList).toHaveBeenCalledTimes(2));
});

it("keeps the route back to Chat's Run optimization control open when the list fails (AC2)", async () => {
  mockList.mockRejectedValue({ status: 500 });

  renderRunsTab();

  // The list failed and says so...
  expect(await screen.findByText("Couldn't load this content.")).toBeInTheDocument();
  // ...but the workspace shell and every tab survive it, so manual Run
  // optimization stays one click away in Chat.
  expect(screen.getByRole("navigation", { name: "Scenario workspace" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Chat" })).toHaveAttribute(
    "href",
    `/scenarios/${scenarioId}`,
  );
  expect(screen.getByRole("link", { name: "Scenario Data" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Runs" })).toBeInTheDocument();
  // Trap 2: the persistent scenario context is not torn down either.
  expect(screen.getByRole("heading", { name: "Fixture A" })).toBeInTheDocument();
});

it("keeps rows on screen when a refetch fails after a page has already loaded (AC2)", async () => {
  const user = userEvent.setup();
  mockList.mockResolvedValueOnce(page() as never).mockRejectedValueOnce({ status: 500 });

  renderRunsTab();
  await screen.findByText("Completed");

  await user.click(screen.getByRole("button", { name: "Refresh" }));

  // AC2: "without hiding saved data". The failed refetch labels the page
  // stale; it does not replace a populated table with a bare alert.
  expect(await screen.findByText(/^Stale —/)).toBeInTheDocument();
  expect(screen.getByText("Completed")).toBeInTheDocument();
  expect(screen.queryByText("Couldn't load this content.")).not.toBeInTheDocument();
});

it("keeps the same navigation open when the scenario simply has no runs yet", async () => {
  mockList.mockResolvedValue(page({ items: [], total_count: 0, matching_count: 0 }) as never);

  renderRunsTab();

  expect(await screen.findByText("No runs yet for this scenario.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Chat" })).toBeInTheDocument();
});
