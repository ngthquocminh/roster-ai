/**
 * SCEN-01 coverage (Wave 0 gap) for all five list states plus the edge
 * behaviors UI-SPEC and the threat model call out. Mocks `useScenarios` with
 * `vi.mock` (never `msw` — `[SLOP]`-rejected, RESEARCH.md/plan 01-02) so each
 * test drives the query hook's states directly rather than a real network
 * boundary.
 *
 * Row-click navigation is asserted against a real `createMemoryRouter` (not a
 * `navigate` spy) so the assertion proves an actual route transition
 * happened, matching this phase's `router.test.tsx` convention.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, useParams } from "react-router";

import { ScenarioTable } from "./ScenarioTable";
import { useScenarios } from "@/hooks/useScenarios";

vi.mock("@/hooks/useScenarios", () => ({
  useScenarios: vi.fn(),
}));

const mockUseScenarios = useScenarios as unknown as ReturnType<typeof vi.fn>;

function ScenarioIdProbe() {
  const { scenarioId } = useParams();
  return <p>navigated-to:{scenarioId}</p>;
}

function renderTable() {
  const router = createMemoryRouter(
    [
      { path: "/", Component: ScenarioTable },
      { path: "/scenarios/:scenarioId", Component: ScenarioIdProbe },
    ],
    { initialEntries: ["/"] },
  );
  return render(<RouterProvider router={router} />);
}

/** Data rows only — excludes the header row (`getAllByRole("row")` includes it). */
function getBodyRows() {
  const table = screen.getByRole("table");
  return within(table).getAllByRole("rowgroup").flatMap((group) => {
    if (group.tagName.toLowerCase() !== "tbody") return [];
    return within(group).getAllByRole("row");
  });
}

function queryResult(overrides: Record<string, unknown>) {
  return {
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
    ...overrides,
  };
}

beforeEach(() => {
  mockUseScenarios.mockReset();
});

describe("ScenarioTable: loading [UI-SPEC E1/loading]", () => {
  it("renders a centered spinner and 'Loading scenarios…' with no table rows and no skeleton", () => {
    mockUseScenarios.mockReturnValue(queryResult({ isLoading: true }));
    renderTable();

    expect(screen.getByText("Loading scenarios…")).toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);
  });
});

describe("ScenarioTable: empty [UI-SPEC E1/empty]", () => {
  it("renders the empty-state heading, body, and an inline 'New Scenario' button — no empty table chrome", () => {
    mockUseScenarios.mockReturnValue(queryResult({ data: [] }));
    renderTable();

    expect(
      screen.getByRole("heading", { name: "No scenarios yet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Create one from a fixture to get started."),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "New Scenario" }),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);
  });
});

describe("ScenarioTable: error [UI-SPEC E1/error]", () => {
  it("renders ErrorBanner and zero table rows — no partial or stale rows", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    mockUseScenarios.mockReturnValue(
      queryResult({ isError: true, error: new Error("network error") }),
    );
    renderTable();

    expect(
      screen.getByText("Couldn't load this content."),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);

    vi.restoreAllMocks();
  });
});

describe("ScenarioTable: populated [UI-SPEC E1/populated]", () => {
  const scenarios = [
    {
      id: "id-1",
      name: "Week 1",
      fixture: "sample_tiny_input.json",
      time_limit_s: 60,
      created_at: "2026-07-10T09:00:00Z",
    },
    {
      id: "id-2",
      name: "Week 2",
      fixture: "sample_large_input.json",
      time_limit_s: 60,
      created_at: "2026-07-09T08:00:00Z",
    },
  ];

  it("renders each row's name, monospace fixture filename, and created timestamp in response order", () => {
    mockUseScenarios.mockReturnValue(queryResult({ data: scenarios }));
    renderTable();

    expect(screen.getByText("Week 1")).toBeInTheDocument();
    expect(screen.getByText("Week 2")).toBeInTheDocument();
    const fixtureCell = screen.getByText("sample_tiny_input.json");
    expect(fixtureCell.className).toMatch(/font-mono/);
    expect(screen.getByText("2026-07-10T09:00:00Z")).toBeInTheDocument();

    const rows = getBodyRows();
    expect(rows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("Week 1"),
      expect.stringContaining("Week 2"),
    ]);
  });

  it("navigates to /scenarios/:scenarioId when a row is clicked", () => {
    mockUseScenarios.mockReturnValue(queryResult({ data: scenarios }));
    renderTable();

    fireEvent.click(screen.getByText("Week 1"));

    expect(screen.getByText("navigated-to:id-1")).toBeInTheDocument();
  });
});

describe("ScenarioTable: adjacency [edge: SCEN-01/adjacency]", () => {
  it("renders two scenarios sharing the same name as two separate rows, keyed by id not name", () => {
    const sameName = [
      {
        id: "id-a",
        name: "duplicate",
        fixture: "f1.json",
        time_limit_s: 60,
        created_at: "2026-07-10T09:00:00Z",
      },
      {
        id: "id-b",
        name: "duplicate",
        fixture: "f2.json",
        time_limit_s: 60,
        created_at: "2026-07-09T08:00:00Z",
      },
    ];
    mockUseScenarios.mockReturnValue(queryResult({ data: sameName }));
    renderTable();

    expect(screen.getAllByText("duplicate")).toHaveLength(2);
    expect(screen.getByText("f1.json")).toBeInTheDocument();
    expect(screen.getByText("f2.json")).toBeInTheDocument();
  });
});

describe("ScenarioTable: ordering [edge: SCEN-01/ordering]", () => {
  it("renders rows sharing an identical created_at in the exact order supplied, with no client-side re-sort", () => {
    const sharedCreatedAt = "2026-07-10T09:00:00Z";
    const rows = [
      {
        id: "id-c",
        name: "third",
        fixture: "f.json",
        time_limit_s: 60,
        created_at: sharedCreatedAt,
      },
      {
        id: "id-a",
        name: "first",
        fixture: "f.json",
        time_limit_s: 60,
        created_at: sharedCreatedAt,
      },
      {
        id: "id-b",
        name: "second",
        fixture: "f.json",
        time_limit_s: 60,
        created_at: sharedCreatedAt,
      },
    ];
    mockUseScenarios.mockReturnValue(queryResult({ data: rows }));
    renderTable();

    const renderedRows = getBodyRows();
    expect(renderedRows.map((row) => row.textContent)).toEqual([
      expect.stringContaining("third"),
      expect.stringContaining("first"),
      expect.stringContaining("second"),
    ]);
  });
});

describe("ScenarioTable: zero-one-many [UI-SPEC E1/zero-one-many]", () => {
  it("renders one row with the same chrome as many, with no count label anywhere", () => {
    mockUseScenarios.mockReturnValue(
      queryResult({
        data: [
          {
            id: "id-only",
            name: "Solo",
            fixture: "f.json",
            time_limit_s: 60,
            created_at: "2026-07-10T09:00:00Z",
          },
        ],
      }),
    );
    const { container } = renderTable();

    expect(getBodyRows()).toHaveLength(1);
    expect(container.textContent).not.toMatch(/\b1 scenario\b/i);
    expect(container.textContent).not.toMatch(/\bscenarios? \(/i);
  });
});

describe("ScenarioTable: HTML-looking name [T-1-03]", () => {
  it("renders a scenario name containing HTML-looking text as literal visible text with no element created from it", () => {
    const maliciousName = '<img src=x onerror="alert(1)">';
    mockUseScenarios.mockReturnValue(
      queryResult({
        data: [
          {
            id: "id-xss",
            name: maliciousName,
            fixture: "f.json",
            time_limit_s: 60,
            created_at: "2026-07-10T09:00:00Z",
          },
        ],
      }),
    );
    const { container } = renderTable();

    expect(screen.getByText(maliciousName)).toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });
});
