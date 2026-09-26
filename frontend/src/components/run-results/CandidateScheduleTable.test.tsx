import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useScenarioProjection", () => ({
  useWorkerNameMap: vi.fn(),
  useTaskNameMap: vi.fn(),
}));

import { useTaskNameMap, useWorkerNameMap } from "@/hooks/useScenarioProjection";
import { CandidateScheduleTable } from "./CandidateScheduleTable";

const row = (i: number, worker = `W${i}`) => ({ record_id: `a${i}`, worker_id: worker, task_id: "T1", shift_id: null, start_minute: 60 * i, end_minute: 60 * i + 90 });

function names(workers?: Map<string, string>, tasks?: Map<string, string>) {
  vi.mocked(useWorkerNameMap).mockReturnValue({ data: workers } as never);
  vi.mocked(useTaskNameMap).mockReturnValue({ data: tasks } as never);
}

describe("CandidateScheduleTable", () => {
  it("renders a table with names, window and duration", () => {
    names(new Map([["W1", "Alice"]]), new Map([["T1", "Picking"]]));
    render(<CandidateScheduleTable assignments={[row(1)]} scenarioId="s" />);
    expect(screen.getByRole("columnheader", { name: "Worker" })).toBeInTheDocument();
    expect(screen.getByText("Alice")).toBeInTheDocument();
    expect(screen.getByText("Picking")).toBeInTheDocument();
    expect(screen.getByText("Day 1, 01:00–02:30")).toBeInTheDocument();
    expect(screen.getByText("1.5 h")).toBeInTheDocument();
  });

  it("falls back to raw IDs when name lookup has no data", () => {
    names();
    render(<CandidateScheduleTable assignments={[row(1)]} scenarioId="s" />);
    expect(screen.getByText("W1")).toBeInTheDocument();
  });

  it("shows an empty state", () => {
    names();
    render(<CandidateScheduleTable assignments={[]} scenarioId="s" />);
    expect(screen.getByText("No assignments")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("sorts by worker name and paginates 25 per page", async () => {
    names();
    const rows = Array.from({ length: 60 }, (_, i) => row(i, `W${String(i).padStart(2, "0")}`)).reverse();
    render(<CandidateScheduleTable assignments={rows} scenarioId="s" />);
    expect(screen.getAllByRole("row")).toHaveLength(26);
    expect(screen.getAllByRole("row")[1]).toHaveTextContent("W00");
    expect(screen.getByText("1–25 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("51–60 of 60")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});
