/**
 * RUN-04/RUN-05 coverage (UI-SPEC E2/E5): loading/error/empty/populated
 * state machine, nullable-timestamp placeholder, FAILED inline error (with
 * its null-defensive fallback), the solver_status-never-rendered
 * prohibition, the T-3-05/T-1-03 HTML-escaping guarantee, zero-one-many
 * chrome parity, and row-click navigation.
 *
 * `runsQuery` is passed directly as a prop (no `vi.mock` needed — this
 * component never calls a hook itself, mirroring OverridesList.test.tsx's
 * approach for the same prop shape). Row-click navigation is asserted
 * against a real `createMemoryRouter` (not a `navigate` spy), matching
 * ScenarioTable.test.tsx's convention.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, within, fireEvent } from "@testing-library/react";
import { createMemoryRouter, RouterProvider, useParams } from "react-router";

import { RunHistoryTable } from "./RunHistoryTable";
import type { components } from "@/api/schema";

type RunOut = components["schemas"]["RunOut"];

function RunProbe() {
  const { scenarioId, runId } = useParams();
  return (
    <p>
      navigated-to:{scenarioId}/{runId}
    </p>
  );
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

function renderTable(
  runsQuery: Record<string, unknown>,
  onTriggerRun?: () => void,
) {
  const router = createMemoryRouter(
    [
      {
        path: "/",
        Component: () => (
          <RunHistoryTable
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            runsQuery={runsQuery as any}
            scenarioId="scenario-1"
            onTriggerRun={onTriggerRun}
          />
        ),
      },
      { path: "/scenarios/:scenarioId/runs/:runId", Component: RunProbe },
    ],
    { initialEntries: ["/"] },
  );
  return render(<RouterProvider router={router} />);
}

/** Data rows only — excludes the header row (`getAllByRole("row")` includes it). */
function getBodyRows() {
  const table = screen.getByRole("table");
  return within(table)
    .getAllByRole("rowgroup")
    .flatMap((group) => {
      if (group.tagName.toLowerCase() !== "tbody") return [];
      return within(group).getAllByRole("row");
    });
}

describe("RunHistoryTable: loading [UI-SPEC E2/loading]", () => {
  it("renders a centered spinner and 'Loading runs…' with no rows", () => {
    renderTable(queryResult({ isLoading: true }));

    expect(screen.getByText("Loading runs…")).toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);
  });
});

describe("RunHistoryTable: error [UI-SPEC E2/error]", () => {
  it("renders ErrorBanner and zero rows — no partial or stale rows", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    renderTable(queryResult({ isError: true, error: new Error("boom") }));

    expect(
      screen.getByText("Can't reach the ShiftMind API."),
    ).toBeInTheDocument();
    expect(screen.queryAllByRole("row")).toHaveLength(0);

    vi.restoreAllMocks();
  });
});

describe("RunHistoryTable: empty [UI-SPEC E2/empty]", () => {
  it("renders the empty heading, body, and an inline 'Run Scenario' button — no table chrome", () => {
    const onTriggerRun = vi.fn();
    renderTable(queryResult({ data: [] }), onTriggerRun);

    expect(
      screen.getByRole("heading", { name: "No runs yet" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("Trigger a run to solve this scenario."),
    ).toBeInTheDocument();

    const button = screen.getByRole("button", { name: "Run Scenario" });
    fireEvent.click(button);
    expect(onTriggerRun).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

const baseRuns: RunOut[] = [
  {
    id: "run-2",
    scenario_id: "scenario-1",
    status: "COMPLETED",
    created_at: "2026-07-18T10:00:00Z",
    started_at: "2026-07-18T10:00:05Z",
    finished_at: "2026-07-18T10:02:00Z",
    solver_status: "OPTIMAL",
    error: null,
  },
  {
    id: "run-1",
    scenario_id: "scenario-1",
    status: "PENDING",
    created_at: "2026-07-18T09:00:00Z",
    started_at: null,
    finished_at: null,
    solver_status: null,
    error: null,
  },
];

describe("RunHistoryTable: populated [UI-SPEC E2/populated]", () => {
  it("renders one row per run in supplied (server) order, with Status/Created/Started/Finished columns", () => {
    renderTable(queryResult({ data: baseRuns }));

    const rows = getBodyRows();
    expect(rows).toHaveLength(2);
    expect(rows[0].textContent).toContain("Completed");
    expect(rows[1].textContent).toContain("Queued");

    expect(
      screen.getByRole("columnheader", { name: "Status" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Created" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Started" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Finished" }),
    ).toBeInTheDocument();
  });

  it("renders nullable started_at/finished_at as a '—' placeholder [UI-SPEC E2/partial]", () => {
    renderTable(queryResult({ data: baseRuns }));

    const rows = getBodyRows();
    // The PENDING row (run-1) has neither started_at nor finished_at.
    const dashCount = (rows[1].textContent?.match(/—/g) ?? []).length;
    expect(dashCount).toBe(2);
  });

  it("navigates to /scenarios/:scenarioId/runs/:runId when a row is clicked", () => {
    renderTable(queryResult({ data: baseRuns }));

    fireEvent.click(screen.getByText("Completed"));

    expect(
      screen.getByText("navigated-to:scenario-1/run-2"),
    ).toBeInTheDocument();
  });
});

describe("RunHistoryTable: FAILED inline error [UI-SPEC E5/RUN-05]", () => {
  it("renders run.error verbatim, wrapped, directly beneath 'Failed'", () => {
    const runs: RunOut[] = [
      {
        id: "run-failed",
        scenario_id: "scenario-1",
        status: "FAILED",
        created_at: "2026-07-18T09:00:00Z",
        started_at: "2026-07-18T09:00:05Z",
        finished_at: "2026-07-18T09:01:00Z",
        solver_status: null,
        error: "Solver crashed: division by zero",
      },
    ];
    renderTable(queryResult({ data: runs }));

    expect(screen.getByText("Failed")).toBeInTheDocument();
    expect(
      screen.getByText("Solver crashed: division by zero"),
    ).toBeInTheDocument();
  });

  it("renders the defensive fallback when error is null [UI-SPEC E5/empty]", () => {
    const runs: RunOut[] = [
      {
        id: "run-failed-null",
        scenario_id: "scenario-1",
        status: "FAILED",
        created_at: "2026-07-18T09:00:00Z",
        started_at: null,
        finished_at: null,
        solver_status: null,
        error: null,
      },
    ];
    renderTable(queryResult({ data: runs }));

    expect(
      screen.getByText("Failed — no error details were recorded."),
    ).toBeInTheDocument();
  });
});

describe("RunHistoryTable: solver_status never rendered [prohibition]", () => {
  it("renders 'Completed' and never the word UNKNOWN, regardless of solver_status", () => {
    const runs: RunOut[] = [
      {
        id: "run-unknown",
        scenario_id: "scenario-1",
        status: "COMPLETED",
        created_at: "2026-07-18T09:00:00Z",
        started_at: "2026-07-18T09:00:05Z",
        finished_at: "2026-07-18T09:01:00Z",
        solver_status: "UNKNOWN",
        error: null,
      },
    ];
    const { container } = renderTable(queryResult({ data: runs }));

    expect(screen.getByText("Completed")).toBeInTheDocument();
    expect(container.textContent).not.toMatch(/UNKNOWN/);
  });
});

describe("RunHistoryTable: HTML-looking error [T-3-05/T-1-03]", () => {
  it("renders an HTML-looking error string as literal text with no element created from it", () => {
    const maliciousError = '<img src=x onerror="alert(1)">';
    const runs: RunOut[] = [
      {
        id: "run-xss",
        scenario_id: "scenario-1",
        status: "FAILED",
        created_at: "2026-07-18T09:00:00Z",
        started_at: null,
        finished_at: null,
        solver_status: null,
        error: maliciousError,
      },
    ];
    const { container } = renderTable(queryResult({ data: runs }));

    expect(screen.getByText(maliciousError)).toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });
});

describe("RunHistoryTable: zero-one-many [UI-SPEC E2/zero-one-many]", () => {
  it("renders one row with identical chrome to many, with no count label anywhere", () => {
    const runs: RunOut[] = [
      {
        id: "run-solo",
        scenario_id: "scenario-1",
        status: "COMPLETED",
        created_at: "2026-07-18T09:00:00Z",
        started_at: "2026-07-18T09:00:05Z",
        finished_at: "2026-07-18T09:01:00Z",
        solver_status: "OPTIMAL",
        error: null,
      },
    ];
    const { container } = renderTable(queryResult({ data: runs }));

    expect(getBodyRows()).toHaveLength(1);
    expect(container.textContent).not.toMatch(/\b1 run\b/i);
    expect(container.textContent).not.toMatch(/\bruns? \(/i);
  });
});
