import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioProjection", () => ({
  useScenarioOverview: vi.fn(), useWorkAreasAndTasks: vi.fn(), useWorkers: vi.fn(),
  useDemand: vi.fn(), useBaselineAssignments: vi.fn(), useLocks: vi.fn(),
  useConstraintsAndObjectives: vi.fn(),
}));
vi.mock("@/hooks/useEvidenceRecord", () => ({ useEvidenceRecord: vi.fn() }));

import { useEvidenceRecord } from "@/hooks/useEvidenceRecord";
import * as hooks from "@/hooks/useScenarioProjection";
import { evidenceHighlights } from "@/test/evidenceHighlights";
import { ScenarioDataView } from "./ScenarioDataView";

const state = { data: undefined, isError: false, isPending: false, refetch: vi.fn() };

function Location() { return <output data-testid="location">{useLocation().search}</output>; }
function renderView(entry = "/data") {
  return render(<MemoryRouter initialEntries={[entry]}><ScenarioDataView scenarioId="scenario-a" /><Location /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(hooks.useScenarioOverview).mockReturnValue(state as never);
  vi.mocked(hooks.useWorkAreasAndTasks).mockReturnValue(state as never);
  vi.mocked(hooks.useWorkers).mockReturnValue(state as never);
  vi.mocked(hooks.useDemand).mockReturnValue(state as never);
  vi.mocked(hooks.useBaselineAssignments).mockReturnValue(state as never);
  vi.mocked(hooks.useLocks).mockReturnValue(state as never);
  vi.mocked(hooks.useConstraintsAndObjectives).mockReturnValue(state as never);
  vi.mocked(useEvidenceRecord).mockReturnValue({ ...state, isSuccess: false } as never);
});

it("forces the cited group and composes the resolved target above its grid", async () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    ...state,
    data: { record_id: "d1", family: "outbound", task_id: "t1", area_id: null, start_minute: 0, end_minute: 30, amount: 1, unit: "volume" },
    isSuccess: true,
  } as never);
  const { container } = renderView("/data?group=demand&record=d1&version=11111111-1111-4111-8111-111111111111&field=amount");

  expect(screen.getByRole("tab", { name: "Demand" })).toHaveAttribute("aria-selected", "true");
  const target = screen.getByRole("region", { name: /Evidence target: Demand d1, amount/ });
  await waitFor(() => expect(target).toHaveFocus());
  expect(target.compareDocumentPosition(screen.getByRole("tabpanel", { name: "Demand" }))).toBe(Node.DOCUMENT_POSITION_FOLLOWING);
  // Decision 2's corollary, asserted where the panel and the grid actually
  // coexist — a per-container count inside the panel's own test cannot see a
  // second highlight rendered by the grid.
  expect(evidenceHighlights(container)).toHaveLength(1);
});

it("keeps the workspace scenario and selected version when the citation names another version", async () => {
  vi.mocked(useEvidenceRecord).mockReturnValue({
    ...state, data: undefined, isError: true, isSuccess: false,
    error: { code: "evidence_version_mismatch", status: 404 },
  } as never);
  render(
    <MemoryRouter initialEntries={["/data?group=demand&record=d1&version=11111111-1111-4111-8111-111111111111"]}>
      <ScenarioDataView scenarioId="scenario-a" selectedVersion="22222222-2222-4222-8222-222222222222" />
      <Location />
    </MemoryRouter>,
  );

  // Task 5: a locator whose version differs from the workspace context renders
  // the mismatch WITHOUT retargeting the surface. The previous assertion drove
  // the panel alone, where nothing could have changed a workspace.
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Version mismatch");
  expect(alert).toHaveTextContent("22222222-2222-4222-8222-222222222222");
  expect(screen.getByTestId("location")).toHaveTextContent("version=11111111-1111-4111-8111-111111111111");
  expect(screen.getByRole("tab", { name: "Demand" })).toHaveAttribute("aria-selected", "true");
  expect(hooks.useScenarioOverview).not.toHaveBeenCalled();
});

it("renders the seven groups in fixed order and defaults to Overview", () => {
  renderView();
  expect(screen.getAllByRole("tab").map(tab => tab.textContent)).toEqual(["Overview", "Work areas and tasks", "Workers", "Demand", "Baseline assignments", "Locks", "Constraints and objectives"]);
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(hooks.useScenarioOverview).toHaveBeenCalledWith("scenario-a");
  expect(hooks.useWorkers).not.toHaveBeenCalled();
});

it("serializes selection and lazily mounts only visited panels", async () => {
  renderView();
  const workers = screen.getByRole("tab", { name: "Workers" });
  workers.focus();
  fireEvent.keyDown(workers, { key: "Enter" });
  await waitFor(() => expect(screen.getByTestId("location")).toHaveTextContent("?group=workers"));
  expect(hooks.useWorkers).toHaveBeenCalledWith("scenario-a", expect.objectContaining({ cursor: 0, limit: 50, order: "asc" }));
  expect(hooks.useDemand).not.toHaveBeenCalled();
});

it("falls back safely from an unknown group", () => {
  renderView("/data?group=garbage");
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("heading", { name: "Scenario Data" })).toBeInTheDocument();
});

it("temporarily reveals a session-hidden evidence field with an explanation", () => {
  sessionStorage.setItem("shiftmind.columns.workers", JSON.stringify(["grade"]));
  vi.mocked(hooks.useWorkers).mockReturnValue({ ...state, data: { items: [{ record_id: "w1", contact_id: "w1", name: "Alex", employment_type: "Full Time", grade: "3", eba: "EA", contracted_hours: 38, qualifications: [], availability_windows: [] }], total_count: 1, matching_count: 1, next_cursor: null } } as never);
  const hidden = renderView("/data?group=workers");
  expect(screen.queryByRole("columnheader", { name: "Grade" })).not.toBeInTheDocument();
  expect(screen.queryByText("3")).not.toBeInTheDocument();
  hidden.unmount();

  renderView("/data?group=workers&field=grade");
  expect(screen.getByRole("columnheader", { name: "Grade" })).toBeInTheDocument();
  expect(screen.getByText("Grade is shown because an evidence link targets it.")).toBeInTheDocument();
});

it("keeps filters and headers mounted for filtered-empty results", () => {
  vi.mocked(hooks.useDemand).mockReturnValue({ ...state, data: { items: [], total_count: 12, matching_count: 0, next_cursor: null } } as never);
  renderView("/data?group=demand&family=outbound");
  expect(screen.getByRole("region", { name: "Filter records" })).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Family" })).toBeInTheDocument();
  expect(screen.getByText("No records in this group match these filters.")).toBeInTheDocument();
});

it("marks stale visible rows busy while the next request is fetching", () => {
  vi.mocked(hooks.useDemand).mockReturnValue({ ...state, isFetching: true, data: { items: [{ record_id: "d1", family: "outbound", task_id: "t1", area_id: null, start_minute: 0, end_minute: 30, amount: 1, unit: "volume" }], total_count: 1, matching_count: 1, next_cursor: null } } as never);
  renderView("/data?group=demand");
  expect(screen.getByRole("region", { name: "Demand" })).toHaveAttribute("aria-busy", "true");
});
