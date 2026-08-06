import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, useLocation } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioProjection", () => ({
  useScenarioOverview: vi.fn(), useWorkAreasAndTasks: vi.fn(), useWorkers: vi.fn(),
  useDemand: vi.fn(), useBaselineAssignments: vi.fn(), useLocks: vi.fn(),
  useConstraintsAndObjectives: vi.fn(),
}));

import * as hooks from "@/hooks/useScenarioProjection";
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
  expect(hooks.useWorkers).toHaveBeenCalledWith("scenario-a");
  expect(hooks.useDemand).not.toHaveBeenCalled();
});

it("falls back safely from an unknown group", () => {
  renderView("/data?group=garbage");
  expect(screen.getByRole("tab", { name: "Overview" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("heading", { name: "Scenario Data" })).toBeInTheDocument();
});
