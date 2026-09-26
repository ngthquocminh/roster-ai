import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
vi.mock("@/hooks/useScenarioProjection", () => ({
  useBaselineAssignments: vi.fn(),
  useTaskNameMap: vi.fn(() => ({ data: undefined })),
  useWorkerNameMap: vi.fn(() => ({ data: undefined })),
}));
import { useBaselineAssignments, useTaskNameMap, useWorkerNameMap } from "@/hooks/useScenarioProjection";
import { BaselineAssignmentsPanel } from "./BaselineAssignmentsPanel";
import { panelTestContract } from "./panelTestContract";

panelTestContract({ name: "BaselineAssignmentsPanel", caption: "Baseline assignments", Panel: BaselineAssignmentsPanel, hook: vi.mocked(useBaselineAssignments), columnHeaders: 5, expected: "worker-1", data: { items: [{ record_id: "a1", worker_id: "worker-1", task_id: "task-1", shift_id: null, start_minute: 480, end_minute: 960 }] } });

describe("BaselineAssignmentsPanel name resolution", () => {
  const refetch = vi.fn();

  it("shows resolved worker and task names while keeping the ID copyable", () => {
    vi.mocked(useBaselineAssignments).mockReturnValue({
      data: { items: [{ record_id: "a1", worker_id: "worker-1", task_id: "task-1", shift_id: null, start_minute: 480, end_minute: 960 }] },
      isError: false, isPending: false, refetch,
    } as never);
    vi.mocked(useWorkerNameMap).mockReturnValue({ data: new Map([["worker-1", "Alex Kim"]]) } as never);
    vi.mocked(useTaskNameMap).mockReturnValue({ data: new Map([["task-1", "Pick"]]) } as never);

    render(<BaselineAssignmentsPanel scenarioId="scenario-a" />);

    expect(screen.getByText("Alex Kim")).toBeInTheDocument();
    expect(screen.getByText("Pick")).toBeInTheDocument();
    expect(screen.queryByText("worker-1")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Worker ID worker-1" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy Task ID task-1" })).toBeInTheDocument();
  });

  it("falls back to the raw ID when no name is resolved yet", () => {
    vi.mocked(useBaselineAssignments).mockReturnValue({
      data: { items: [{ record_id: "a1", worker_id: "worker-1", task_id: "task-1", shift_id: null, start_minute: 480, end_minute: 960 }] },
      isError: false, isPending: false, refetch,
    } as never);
    vi.mocked(useWorkerNameMap).mockReturnValue({ data: undefined } as never);
    vi.mocked(useTaskNameMap).mockReturnValue({ data: undefined } as never);

    render(<BaselineAssignmentsPanel scenarioId="scenario-a" />);

    expect(screen.getByText("worker-1")).toBeInTheDocument();
    expect(screen.getByText("task-1")).toBeInTheDocument();
  });
});
