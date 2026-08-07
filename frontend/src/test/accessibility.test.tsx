import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import { axe } from "jest-axe";
import type { ComponentProps, ReactNode } from "react";
import { createMemoryRouter, MemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioProjection", () => ({
  useScenarioOverview: vi.fn(),
  useWorkAreasAndTasks: vi.fn(),
  useWorkers: vi.fn(),
  useDemand: vi.fn(),
  useBaselineAssignments: vi.fn(),
  useLocks: vi.fn(),
  useConstraintsAndObjectives: vi.fn(),
}));
vi.mock("@/hooks/useScenarioContext", () => ({ useScenarioContext: vi.fn() }));

import { PRIMITIVE_FIXTURES } from "@/components/primitives/fixtures";
import { FixtureCatalogueView } from "@/features/fixture-catalogue/FixtureCatalogueView";
import { ScenarioDataView } from "@/features/scenario-data/ScenarioDataView";
import * as projectionHooks from "@/hooks/useScenarioProjection";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { ScenarioWorkspace } from "@/routes/ScenarioWorkspace";

type Contract = Readonly<{
  fixture: { fixture_id: string; version: string };
  overview: Record<string, unknown>;
  groups: Record<string, Array<Record<string, unknown>>>;
}>;

const contract = JSON.parse(
  readFileSync(resolve(process.cwd(), "../data/contract/sample_tiny_input.projection-v1.json"), "utf8"),
) as Contract;
const scenarioId = "11111111-1111-4111-8111-111111111111";
const context = {
  schema_version: "v1",
  scenario_name: contract.fixture.fixture_id,
  scenario_id: scenarioId,
  fixture_version: contract.fixture.version,
  checksum_algorithm: "sha256",
  checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64),
  site_id: "22222222-2222-4222-8222-222222222222",
  baseline_schedule_version: null,
};
const queryBase = { error: null, isError: false, isFetching: false, isPending: false, refetch: vi.fn() };

async function expectClean(container: HTMLElement) {
  const results = await axe(container, { rules: { "color-contrast": { enabled: false } } });
  expect(results.violations).toEqual([]);
}

function withRouter(node: ReactNode, entry = "/") {
  return <MemoryRouter initialEntries={[entry]}>{node}</MemoryRouter>;
}

describe("accessibility axe sweep", () => {
  beforeEach(() => {
    sessionStorage.clear();
    vi.clearAllMocks();
  });

  const catalogueEntry = {
    ...context,
    fixture_id: contract.fixture.fixture_id,
    scenario_version_id: "33333333-3333-4333-8333-333333333333",
    imported_at: "2026-08-06T00:00:00Z",
  };
  const catalogueStates: Array<[string, Omit<ComponentProps<typeof FixtureCatalogueView>, "onRetry">]> = [
    ["loading", { data: undefined, isError: false, isPending: true }],
    ["empty", { data: [], isError: false, isPending: false }],
    ["error", { data: undefined, isError: true, isPending: false }],
    ["loaded", { data: [catalogueEntry], isError: false, isPending: false }],
    ["stale", { data: [catalogueEntry], isError: true, isPending: false }],
  ];

  for (const [name, state] of catalogueStates) {
    it(`keeps the fixture catalogue ${name} state axe-clean`, async () => {
      const { container } = render(withRouter(
        <FixtureCatalogueView {...state} onRetry={vi.fn()} />,
      ));
      await expectClean(container);
    });
  }

  for (const fixture of PRIMITIVE_FIXTURES) {
    it(`keeps ${fixture.primitive}/${fixture.state} axe-clean`, async () => {
      const { container } = render(<>{fixture.render()}</>);
      await expectClean(container);
    });
  }

  const workspaceStates = [
    ["pending", { ...queryBase, data: undefined, isPending: true }],
    ["terminal", { ...queryBase, data: undefined, error: { status: 404 }, isError: true }],
    ["error", { ...queryBase, data: undefined, error: { status: 503 }, isError: true }],
    ["loaded", { ...queryBase, data: context }],
  ] as const;

  for (const [name, state] of workspaceStates) {
    it(`keeps the scenario workspace ${name} state axe-clean`, async () => {
      vi.mocked(useScenarioContext).mockReturnValue(state as never);
      const router = createMemoryRouter(
        [{ path: "/scenarios/:scenarioId", Component: ScenarioWorkspace, children: [{ index: true, element: <p>Child view</p> }] }],
        { initialEntries: [`/scenarios/${scenarioId}`] },
      );
      const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
      const { container } = render(<QueryClientProvider client={client}><RouterProvider router={router} /></QueryClientProvider>);
      await expectClean(container);
    });
  }

  const groups = [
    "overview",
    "work-areas-and-tasks",
    "workers",
    "demand",
    "baseline-assignments",
    "locks",
    "constraints-and-objectives",
  ] as const;
  const hookByGroup = {
    "work-areas-and-tasks": projectionHooks.useWorkAreasAndTasks,
    workers: projectionHooks.useWorkers,
    demand: projectionHooks.useDemand,
    "baseline-assignments": projectionHooks.useBaselineAssignments,
    locks: projectionHooks.useLocks,
    "constraints-and-objectives": projectionHooks.useConstraintsAndObjectives,
  } as const;

  for (const group of groups) {
    for (const state of ["loading", "empty", "error", "loaded"] as const) {
      it(`keeps Scenario Data ${group}/${state} axe-clean`, async () => {
        const data = group === "overview"
          ? { ...contract.overview, scenario_name: contract.fixture.fixture_id, scenario_id: scenarioId, fixture_version: "v1", projection_generated_at: "2026-08-06T00:00:00Z" }
          : { items: contract.groups[group].slice(0, 1), total_count: contract.groups[group].length, matching_count: contract.groups[group].length, next_cursor: null };
        const queryState = state === "loading"
          ? { ...queryBase, data: undefined, isPending: true }
          : state === "error"
            ? { ...queryBase, data: undefined, error: { status: 503 }, isError: true }
            : { ...queryBase, data: state === "empty" ? (group === "overview" ? null : { items: [], total_count: 0, matching_count: 0, next_cursor: null }) : data };
        if (group === "overview") {
          vi.mocked(projectionHooks.useScenarioOverview).mockReturnValue(queryState as never);
        } else {
          vi.mocked(hookByGroup[group]).mockReturnValue(queryState as never);
        }
        const { container } = render(withRouter(
          <ScenarioDataView scenarioId={scenarioId} />,
          `/data?group=${group}`,
        ));
        await expectClean(container);
      });
    }
  }
});
