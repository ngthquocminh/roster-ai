import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

import { ScenarioDataView } from "@/features/scenario-data/ScenarioDataView";
import { ScenarioVersionContext } from "@/features/scenario-workspace/ScenarioVersionContext";
import { WorkspaceTabs } from "@/features/scenario-workspace/WorkspaceTabs";
import * as hooks from "@/hooks/useScenarioProjection";

type Contract = Readonly<{
  fixture: { fixture_id: string; version: string };
  overview: Record<string, unknown>;
  groups: Record<string, Array<Record<string, unknown>>>;
}>;
const contract = JSON.parse(
  readFileSync(resolve(process.cwd(), "../data/contract/sample_tiny_input.projection-v1.json"), "utf8"),
) as Contract;
const scenarioId = "11111111-1111-4111-8111-111111111111";
const queryBase = { error: null, isError: false, isFetching: false, isPending: false, refetch: vi.fn() };
const hookByGroup = {
  "work-areas-and-tasks": hooks.useWorkAreasAndTasks,
  workers: hooks.useWorkers,
  demand: hooks.useDemand,
  "baseline-assignments": hooks.useBaselineAssignments,
  locks: hooks.useLocks,
  "constraints-and-objectives": hooks.useConstraintsAndObjectives,
} as const;

function page(group: keyof typeof hookByGroup) {
  const fallbacks: Partial<Record<keyof typeof hookByGroup, Record<string, unknown>>> = {
    "baseline-assignments": { record_id: "assignment-1", worker_id: "worker-1", task_id: "task-1", shift_id: "shift-1", start_minute: 0, end_minute: 30 },
    locks: { record_id: "lock-1", target_type: "worker", target_ref: "worker-1", scope: "assignment", source: "fixture" },
  };
  const items = contract.groups[group].length > 0
    ? contract.groups[group].slice(0, 1)
    : [fallbacks[group]!];
  return { items, matching_count: items.length, next_cursor: null, total_count: items.length };
}

beforeEach(() => {
  sessionStorage.clear();
  vi.clearAllMocks();
  for (const [group, hook] of Object.entries(hookByGroup)) {
    vi.mocked(hook).mockReturnValue({ ...queryBase, data: page(group as keyof typeof hookByGroup) } as never);
  }
  vi.mocked(hooks.useScenarioOverview).mockReturnValue({
    ...queryBase,
    data: {
      ...contract.overview,
      scenario_name: contract.fixture.fixture_id,
      scenario_id: scenarioId,
      fixture_version: contract.fixture.version,
      projection_generated_at: "2026-08-06T00:00:00Z",
    },
  } as never);
});

it("preserves heading hierarchy and keyboard reading order through Scenario Data controls", async () => {
  const user = userEvent.setup();
  const { container } = render(
    <MemoryRouter initialEntries={[`/scenarios/${scenarioId}/data?group=demand&family=outbound`]}>
      <main>
        <ScenarioVersionContext context={{
          schema_version: "v1",
          scenario_name: contract.fixture.fixture_id,
          scenario_id: scenarioId,
          scenario_version_id: "33333333-3333-4333-8333-333333333333",
          fixture_version: contract.fixture.version,
          checksum_algorithm: "sha256",
          checksum_schema_version: "rfc8785-v1",
          checksum_digest: "a".repeat(64),
          site_id: "22222222-2222-4222-8222-222222222222",
          baseline_schedule_version: null,
        }} />
        <WorkspaceTabs scenarioId={scenarioId} />
        <ScenarioDataView scenarioId={scenarioId} />
      </main>
    </MemoryRouter>,
  );

  expect(Array.from(container.querySelectorAll("h1, h2, h3")).map((heading) => `${heading.tagName}:${heading.textContent}`)).toEqual([
    `H1:${contract.fixture.fixture_id}`,
    "H2:Scenario Data",
  ]);
  expect(screen.getByRole("link", { name: "Scenario Data" })).toHaveAttribute("aria-current", "page");
  expect(screen.getByRole("tab", { name: "Demand" })).toHaveAttribute("aria-selected", "true");
  expect(screen.getByRole("button", { name: "Remove Family filter" })).toHaveTextContent("Family: Outbound");

  const order = [
    screen.getByRole("link", { name: "Change scenario" }),
    screen.getByRole("link", { name: "Chat" }),
    screen.getByRole("link", { name: "Scenario Data" }),
    screen.getByRole("link", { name: "Runs" }),
    screen.getByRole("tab", { name: "Demand" }),
    screen.getByRole("button", { name: "Choose columns" }),
    screen.getByRole("combobox", { name: "Family" }),
    screen.getByRole("textbox", { name: "Task ID" }),
    screen.getByRole("textbox", { name: "Area ID" }),
    screen.getByRole("spinbutton", { name: "Start minute at or after" }),
    screen.getByRole("spinbutton", { name: "End minute at or before" }),
    screen.getByRole("button", { name: "Apply" }),
    screen.getByRole("button", { name: "Clear" }),
    screen.getByRole("button", { name: "Remove Family filter" }),
    screen.getByRole("tabpanel", { name: "Demand" }),
    screen.getByRole("region", { name: "Demand" }),
    screen.getByRole("button", { name: "Sort by Family" }),
  ];
  for (const expected of order) {
    await user.tab();
    expect(expected).toHaveFocus();
  }

  expect(container.querySelector("td[tabindex]")).toBeNull();
  expect(screen.getByRole("region", { name: "Demand" })).toHaveAttribute("tabindex", "0");
});

for (const group of Object.keys(hookByGroup) as Array<keyof typeof hookByGroup>) {
  it(`provides a captioned, keyboard-scrollable ${group} table region`, () => {
    const { container } = render(
      <MemoryRouter initialEntries={[`/data?group=${group}`]}>
        <ScenarioDataView scenarioId={scenarioId} />
      </MemoryRouter>,
    );
    const region = screen.getByRole("region", { name: new RegExp(group.replaceAll("-", " "), "i") });
    expect(region).toHaveAttribute("tabindex", "0");
    const caption = container.querySelector("caption");
    expect(caption).toHaveClass("sr-only");
    expect(caption?.textContent).toBe(region.getAttribute("aria-label"));
  });
}
