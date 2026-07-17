/**
 * Route-level integration coverage for the composed Editor (SCEN-03 +
 * CONS-01..05): the fixed-order populated render, transcript-append +
 * textarea-clear on a full apply, transcript-append + textarea-preservation
 * on a clarification outcome, and the 404 terminal gate (E7).
 *
 * Mocks `@/api/scenarios` (`getScenario`, `getScenarioOverrides`) and
 * `@/api/constraints` (`applyConstraint`) at the module boundary — repo
 * convention, never msw (see `CreateScenarioDialog.test.tsx`) — so the real
 * `useScenario`/`useOverrides`/`useApplyConstraint` hooks drive genuine
 * query/mutation state through a real `QueryClient`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createMemoryRouter, RouterProvider } from "react-router";

vi.mock("@/api/scenarios", () => ({
  getScenario: vi.fn(),
  getScenarioOverrides: vi.fn(),
}));
vi.mock("@/api/constraints", () => ({
  applyConstraint: vi.fn(),
}));

import { getScenario, getScenarioOverrides } from "@/api/scenarios";
import { applyConstraint } from "@/api/constraints";
import { Editor } from "./Editor";

const mockGetScenario = getScenario as unknown as ReturnType<typeof vi.fn>;
const mockGetScenarioOverrides = getScenarioOverrides as unknown as ReturnType<
  typeof vi.fn
>;
const mockApplyConstraint = applyConstraint as unknown as ReturnType<
  typeof vi.fn
>;

const SCENARIO = {
  id: "s1",
  name: "Week 1",
  fixture: "sample_tiny_input.json",
  time_limit_s: 60,
  created_at: "2026-01-01T00:00:00Z",
};

function renderEditor(path = "/scenarios/s1") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId", Component: Editor }],
    { initialEntries: [path] },
  );
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mockGetScenario.mockReset();
  mockGetScenarioOverrides.mockReset();
  mockApplyConstraint.mockReset();
});

describe("Editor: populated [SCEN-03, UI-SPEC Application Structure]", () => {
  it("renders header + empty-overrides state + the input, with no transcript chrome initially", async () => {
    mockGetScenario.mockResolvedValueOnce(SCENARIO);
    mockGetScenarioOverrides.mockResolvedValueOnce([]);
    const { container } = renderEditor();

    expect(
      await screen.findByRole("heading", { name: "Week 1" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("heading", { name: "No constraints applied yet" }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText("Constraint text")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Apply Constraint" }),
    ).toBeInTheDocument();
    // ConstraintTranscript renders nothing (not even chrome) until the
    // first submission — no bordered list container exists yet (neither
    // the transcript's nor a populated OverridesList's, since overrides
    // resolved empty).
    expect(container.querySelectorAll(".border-border").length).toBe(0);
  });
});

describe("Editor: apply outcome [CONS-01, CONS-02, D-03]", () => {
  it("appends a transcript entry showing the parsed_constraint and clears the textarea on a full apply", async () => {
    mockGetScenario.mockResolvedValueOnce(SCENARIO);
    mockGetScenarioOverrides.mockResolvedValueOnce([]);
    mockApplyConstraint.mockResolvedValueOnce({
      applied: [
        {
          id: "c1",
          tool: "set_min_workers_per_task",
          args: {},
          parsed_constraint: "At least 2 workers on Pick",
        },
      ],
      rejected: [],
      clarification_needed: null,
      no_constraint_found: false,
    });
    renderEditor();
    await screen.findByRole("heading", { name: "Week 1" });

    const textarea = screen.getByLabelText(
      "Constraint text",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, {
      target: { value: "keep 2 workers on Pick" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(
      await screen.findByText("At least 2 workers on Pick"),
    ).toBeInTheDocument();
    await waitFor(() => expect(textarea.value).toBe(""));
  });
});

describe("Editor: clarification outcome [CONS-04]", () => {
  it("appends a transcript entry and preserves the typed text on clarification_needed", async () => {
    mockGetScenario.mockResolvedValueOnce(SCENARIO);
    mockGetScenarioOverrides.mockResolvedValueOnce([]);
    mockApplyConstraint.mockResolvedValueOnce({
      applied: [],
      rejected: [],
      clarification_needed: "Which worker?",
      no_constraint_found: false,
    });
    renderEditor();
    await screen.findByRole("heading", { name: "Week 1" });

    const textarea = screen.getByLabelText(
      "Constraint text",
    ) as HTMLTextAreaElement;
    fireEvent.change(textarea, { target: { value: "lock a shift" } });
    fireEvent.click(screen.getByRole("button", { name: "Apply Constraint" }));

    expect(
      await screen.findByText(/Needs clarification: Which worker\?/),
    ).toBeInTheDocument();
    expect(textarea.value).toBe("lock a shift");
  });
});

describe("Editor: 404 gate [E7]", () => {
  it("renders only the Scenario not found terminal view — no input or overrides regions, no overrides fetch", async () => {
    mockGetScenario.mockRejectedValueOnce({ status: 404 });
    renderEditor();

    expect(
      await screen.findByRole("heading", { name: "Scenario not found" }),
    ).toBeInTheDocument();
    expect(screen.queryByLabelText("Constraint text")).not.toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "Applied Overrides" }),
    ).not.toBeInTheDocument();
    expect(mockGetScenarioOverrides).not.toHaveBeenCalled();
  });
});
