import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { FILTERS_BY_GROUP } from "./filters";
import { FilterBar } from "./FilterBar";

describe("FilterBar", () => {
  it("keeps typing in draft state until Apply and serializes non-empty fields", () => {
    const onApply = vi.fn();
    render(<FilterBar activeFilters={{}} filters={FILTERS_BY_GROUP["work-areas-and-tasks"]} onApply={onApply} onClear={vi.fn()} onRemove={vi.fn()} />);
    fireEvent.change(screen.getByLabelText("Task ID"), { target: { value: "T-104" } });
    fireEvent.change(screen.getByLabelText("Name contains"), { target: { value: "" } });
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Apply" }));
    expect(onApply).toHaveBeenCalledWith({ task_id: "T-104" });
  });

  it("shows an active count, supports individual removal, and clears all", () => {
    const onClear = vi.fn();
    const onRemove = vi.fn();
    render(<FilterBar activeFilters={{ family: "outbound", task_id: "T-104" }} filters={FILTERS_BY_GROUP.demand} onApply={vi.fn()} onClear={onClear} onRemove={onRemove} />);
    expect(screen.getByText("2 active filters")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Remove Family filter" }));
    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(onRemove).toHaveBeenCalledWith("family");
    expect(onClear).toHaveBeenCalledOnce();
  });

  it("closes a select with Escape, restores trigger focus, and commits nothing", async () => {
    const user = userEvent.setup();
    const onApply = vi.fn();
    render(<FilterBar activeFilters={{}} filters={FILTERS_BY_GROUP.demand} onApply={onApply} onClear={vi.fn()} onRemove={vi.fn()} />);
    const trigger = screen.getByRole("combobox", { name: "Family" });
    await user.click(trigger);
    expect(await screen.findByRole("option", { name: "Outbound" })).toBeInTheDocument();
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("option", { name: "Outbound" })).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(onApply).not.toHaveBeenCalled();
  });
});
