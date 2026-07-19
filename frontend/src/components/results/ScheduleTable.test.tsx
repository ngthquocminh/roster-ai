/**
 * RES-03 coverage (UI-SPEC E6): server-order-only rendering (no client
 * re-sort — D-09), the Shift Window cell via `formatShiftWindow` (D-10),
 * and the honest empty state for a COMPLETED run with zero scheduled shifts
 * (a legitimate solver outcome, not an error).
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { ScheduleTable } from "./ScheduleTable";
import type { ScheduleRow } from "@/api/results";

function getBodyRows() {
  const table = screen.getByRole("table");
  return within(table).getAllByRole("rowgroup").flatMap((group) => {
    if (group.tagName.toLowerCase() !== "tbody") return [];
    return within(group).getAllByRole("row");
  });
}

const rows: ScheduleRow[] = [
  {
    contact_id: "c-2",
    member_name: "Bob",
    task_id: "task-pack",
    function: "Pack",
    shift_id: "shift-2",
    start_h: 30,
    end_h: 38,
  },
  {
    contact_id: "c-1",
    member_name: "Alice",
    task_id: "task-pick",
    function: "Pick",
    shift_id: "shift-1",
    start_h: 6,
    end_h: 14,
  },
];

describe("ScheduleTable: populated [UI-SPEC E6/populated]", () => {
  it("renders one row per schedule row in given (server) order, not sorted", () => {
    render(<ScheduleTable schedule={rows} />);

    const bodyRows = getBodyRows();
    expect(bodyRows).toHaveLength(2);
    // First input row is Bob/Pack — must remain first, not re-sorted
    // alphabetically (which would put Alice first).
    expect(bodyRows[0].textContent).toContain("Bob");
    expect(bodyRows[1].textContent).toContain("Alice");
  });

  it("renders Member/Task/Function/Shift Window columns", () => {
    render(<ScheduleTable schedule={rows} />);

    expect(
      screen.getByRole("columnheader", { name: "Member" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Task" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Function" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: "Shift Window" }),
    ).toBeInTheDocument();
  });

  it("formats the Shift Window cell via formatShiftWindow", () => {
    render(<ScheduleTable schedule={rows} />);

    // Bob: start_h=30 -> Day 2, 06:00; end_h=38 -> Day 2, 14:00
    expect(screen.getByText("Day 2, 06:00–14:00")).toBeInTheDocument();
    // Alice: start_h=6 -> Day 1, 06:00; end_h=14 -> Day 1, 14:00
    expect(screen.getByText("Day 1, 06:00–14:00")).toBeInTheDocument();
  });

  it("renders member_name/task_id/function as plain text, no dangerouslySetInnerHTML sink", () => {
    const maliciousRows: ScheduleRow[] = [
      {
        contact_id: "c-x",
        member_name: '<img src=x onerror="alert(1)">',
        task_id: "task-x",
        function: "Pick",
        shift_id: "shift-x",
        start_h: 0,
        end_h: 8,
      },
    ];
    const { container } = render(<ScheduleTable schedule={maliciousRows} />);

    expect(
      screen.getByText('<img src=x onerror="alert(1)">'),
    ).toBeInTheDocument();
    expect(container.querySelector("img")).not.toBeInTheDocument();
  });
});

describe("ScheduleTable: empty [UI-SPEC E6/empty]", () => {
  it("renders the empty-state copy instead of a table for zero scheduled shifts", () => {
    render(<ScheduleTable schedule={[]} />);

    expect(
      screen.getByText("No shifts were scheduled for this run."),
    ).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("ScheduleTable: zero-one-many [UI-SPEC zero-one-many]", () => {
  it("renders one row with identical chrome to many", () => {
    render(<ScheduleTable schedule={[rows[0]]} />);

    expect(getBodyRows()).toHaveLength(1);
  });
});
