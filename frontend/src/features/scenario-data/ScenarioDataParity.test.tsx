import { readFileSync } from "node:fs";
import { join } from "node:path";

import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { beforeEach, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioProjection", () => ({
  useScenarioOverview: vi.fn(),
  useWorkAreasAndTasks: vi.fn(),
  useWorkers: vi.fn(),
  useDemand: vi.fn(),
  useBaselineAssignments: vi.fn(),
  useLocks: vi.fn(),
  useConstraintsAndObjectives: vi.fn(),
}));

import * as hooks from "@/hooks/useScenarioProjection";
import { formatMinuteWindow } from "@/lib/formatShiftWindow";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { ScenarioDataView } from "./ScenarioDataView";

type JsonRecord = Record<string, unknown>;
type ContractFixture = {
  fixture: { fixture_id: string; version: string };
  overview: JsonRecord;
  groups: Record<string, JsonRecord[]>;
};

const FIXTURES = ["sample_tiny_input", "sample_tiny_input_more_tm"] as const;
const LIST_GROUPS = [
  "work-areas-and-tasks",
  "workers",
  "demand",
  "baseline-assignments",
  "locks",
  "constraints-and-objectives",
] as const;

function loadContract(fixtureId: string): ContractFixture {
  return JSON.parse(
    readFileSync(
      join(process.cwd(), "../data/contract", `${fixtureId}.projection-v1.json`),
      "utf8",
    ),
  ) as ContractFixture;
}

function queryState(data: unknown) {
  return {
    data,
    isError: false,
    isFetching: false,
    isPending: false,
    refetch: vi.fn(),
  };
}

function pageImplementation(items: JsonRecord[]) {
  return ((_scenarioId: string, params: { cursor?: number; limit?: number } = {}) => {
    const cursor = params.cursor ?? 0;
    const limit = params.limit ?? 50;
    const page = items.slice(cursor, cursor + limit);
    const end = cursor + page.length;
    return queryState({
      items: page,
      matching_count: items.length,
      next_cursor: end < items.length ? end : null,
      total_count: items.length,
    });
  }) as never;
}

function installContract(contract: ContractFixture) {
  const overview = contract.overview;
  vi.mocked(hooks.useScenarioOverview).mockReturnValue(
    queryState({
      ...overview,
      scenario_name: contract.fixture.fixture_id,
      scenario_id: contract.fixture.fixture_id,
      fixture_version: contract.fixture.version,
      projection_generated_at: "2026-08-06T00:00:00Z",
    }) as never,
  );
  vi.mocked(hooks.useWorkAreasAndTasks).mockImplementation(pageImplementation(contract.groups["work-areas-and-tasks"]));
  vi.mocked(hooks.useWorkers).mockImplementation(pageImplementation(contract.groups.workers));
  vi.mocked(hooks.useDemand).mockImplementation(pageImplementation(contract.groups.demand));
  vi.mocked(hooks.useBaselineAssignments).mockImplementation(pageImplementation(contract.groups["baseline-assignments"]));
  vi.mocked(hooks.useLocks).mockImplementation(pageImplementation(contract.groups.locks));
  vi.mocked(hooks.useConstraintsAndObjectives).mockImplementation(pageImplementation(contract.groups["constraints-and-objectives"]));
}

function text(value: unknown): string {
  return value === null || value === undefined ? "—" : String(value);
}

function nestedList(value: unknown, format: (item: JsonRecord) => string): string {
  const items = value as JsonRecord[];
  return items.length ? items.map(format).join(", ") : "—";
}

function expectedCells(group: typeof LIST_GROUPS[number], item: JsonRecord): string[] {
  switch (group) {
    case "work-areas-and-tasks":
      return ["task_id", "name", "function", "area_id", "area_name", "unit_type_id"].map((key) => text(item[key]));
    case "workers":
      return [
        text(item.contact_id),
        text(item.name),
        text(item.employment_type),
        text(item.grade),
        text(item.eba),
        text(item.contracted_hours),
        nestedList(item.qualifications, (qualification) => `${qualification.task_id} (${qualification.rate})`),
        (item.availability_windows as JsonRecord[]).length
          ? (item.availability_windows as JsonRecord[])
              .map((window) => `${window.kind} ${formatMinuteWindow(Number(window.start_minute), Number(window.end_minute))}`)
              .join("; ")
          : "—",
      ];
    case "demand":
      return [
        text(item.record_id),
        text(item.family),
        text(item.task_id),
        text(item.area_id),
        formatMinuteWindow(Number(item.start_minute), Number(item.end_minute)),
        text(item.amount),
        text(item.unit),
      ];
    case "baseline-assignments":
      return [
        text(item.record_id),
        text(item.worker_id),
        text(item.task_id),
        text(item.shift_id),
        formatMinuteWindow(Number(item.start_minute), Number(item.end_minute)),
      ];
    case "locks":
      return ["record_id", "target_type", "target_ref", "scope", "source"].map((key) => text(item[key]));
    case "constraints-and-objectives":
      return ["record_id", "constraint_type", "value", "value_type"].map((key) => text(item[key]));
  }
}

function renderedRows(caption: string): string[][] {
  const table = screen.getByText(caption, { selector: "caption" }).closest("table");
  if (!table) throw new Error(`Missing ${caption} table`);
  return Array.from(table.querySelectorAll("tbody tr"), (row) =>
    Array.from(row.querySelectorAll("th, td"), (cell) => cell.textContent ?? ""),
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
});

for (const fixtureId of FIXTURES) {
  it(`renders every contract overview value for ${fixtureId}`, () => {
    const contract = loadContract(fixtureId);
    installContract(contract);
    render(
      <MemoryRouter initialEntries={["/data?group=overview"]}>
        <ScenarioDataView scenarioId={fixtureId} />
      </MemoryRouter>,
    );

    const overview = contract.overview;
    expect(renderedRows("Overview")).toEqual([
      ["Scenario name", contract.fixture.fixture_id],
      ["Scenario ID", contract.fixture.fixture_id],
      ["Fixture version", contract.fixture.version],
      ["Baseline version", "Not established"],
      ["Time horizon", `starts ${formatTimestamp(String(overview.horizon_start))}, ${overview.horizon_minutes} minutes`],
      ["Site timezone", text(overview.site_timezone)],
      ["Last verified", "2026-08-06 00:00"],
      ["Work areas", text(overview.work_area_count)],
      ["Tasks", text(overview.task_count)],
      ["Workers", text(overview.worker_count)],
      ["Demand intervals", text(overview.demand_interval_count)],
      ["Baseline assignments", text(overview.baseline_assignment_count)],
      ["Locks", text(overview.lock_count)],
      ["Constraints and objectives", text(overview.constraint_count)],
    ]);
  });

  for (const group of LIST_GROUPS) {
    it(`renders every ${group} contract cell across all pages for ${fixtureId}`, () => {
      const contract = loadContract(fixtureId);
      installContract(contract);
      const items = contract.groups[group];
      if (items.length === 0) {
        render(
          <MemoryRouter initialEntries={[`/data?group=${group}`]}>
            <ScenarioDataView scenarioId={fixtureId} />
          </MemoryRouter>,
        );
        expect(screen.getByText("This fixture has no records in this group.")).toBeInTheDocument();
        return;
      }

      const observed: string[][] = [];
      for (let cursor = 0; cursor < items.length; cursor += 50) {
        const view = render(
          <MemoryRouter initialEntries={[`/data?group=${group}&cursor=${cursor}`]}>
            <ScenarioDataView scenarioId={fixtureId} />
          </MemoryRouter>,
        );
        observed.push(...renderedRows(group === "constraints-and-objectives" ? "Constraints and objectives" : group.split("-").map((part, index) => index === 0 ? `${part[0].toUpperCase()}${part.slice(1)}` : part).join(" ")));
        view.unmount();
      }
      expect(observed).toEqual(items.map((item) => expectedCells(group, item)));
    }, 60_000);
  }
}
