import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { COLUMNS_BY_GROUP } from "./columns";
import { ScenarioDataHeader } from "./ScenarioDataTable";

describe("ScenarioDataHeader", () => {
  it("exposes one sortable aria state and leaves non-sortable columns plain", () => {
    const onSort = vi.fn();
    const { rerender } = render(<table><ScenarioDataHeader columns={COLUMNS_BY_GROUP.demand} onSort={onSort} order="asc" /></table>);
    const family = screen.getByRole("columnheader", { name: "Family" });
    const unit = screen.getByRole("columnheader", { name: "Unit" });
    expect(family).toHaveAttribute("scope", "col");
    expect(family).toHaveAttribute("aria-sort", "none");
    expect(unit).not.toHaveAttribute("aria-sort");
    expect(screen.queryByRole("button", { name: /Sort by Unit/ })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Sort by Family" }));
    expect(onSort).toHaveBeenCalledWith("family");
    rerender(<table><ScenarioDataHeader columns={COLUMNS_BY_GROUP.demand} onSort={onSort} order="desc" sort="family" /></table>);
    expect(screen.getByRole("columnheader", { name: "Family" })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getAllByRole("columnheader").filter((header) => header.getAttribute("aria-sort") === "descending")).toHaveLength(1);
  });
});
