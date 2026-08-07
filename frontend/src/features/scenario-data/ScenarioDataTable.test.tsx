import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { COLUMNS_BY_GROUP, type ColumnDef } from "./columns";
import { ScenarioDataHeader } from "./ScenarioDataTable";

describe("ScenarioDataHeader", () => {
  for (const [group, columns] of Object.entries(COLUMNS_BY_GROUP)) {
    it(`exposes exactly one sortable aria state for ${group} and leaves non-sortable columns plain`, () => {
    const onSort = vi.fn();
    const normalized = columns as readonly ColumnDef[];
    const sortable = normalized.find((column) => column.sortKey);
    expect(sortable).toBeDefined();
    const { rerender } = render(<table><ScenarioDataHeader columns={normalized} onSort={onSort} order="asc" /></table>);
    expect(screen.getByRole("columnheader", { name: sortable?.header })).toHaveAttribute("aria-sort", "none");
    rerender(<table><ScenarioDataHeader columns={normalized} onSort={onSort} order="asc" sort={sortable?.sortKey} /></table>);
    const active = screen.getByRole("columnheader", { name: sortable?.header });
    expect(active).toHaveAttribute("scope", "col");
    expect(active).toHaveAttribute("aria-sort", "ascending");
    for (const column of normalized.filter((candidate) => !candidate.sortKey)) {
      expect(screen.getByRole("columnheader", { name: column.header })).not.toHaveAttribute("aria-sort");
      expect(screen.queryByRole("button", { name: `Sort by ${column.header}` })).not.toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole("button", { name: `Sort by ${sortable?.header}` }));
    expect(onSort).toHaveBeenCalledWith(sortable?.sortKey);
    rerender(<table><ScenarioDataHeader columns={normalized} onSort={onSort} order="desc" sort={sortable?.sortKey} /></table>);
    expect(screen.getByRole("columnheader", { name: sortable?.header })).toHaveAttribute("aria-sort", "descending");
    expect(screen.getAllByRole("columnheader").filter((header) => header.getAttribute("aria-sort") === "descending")).toHaveLength(1);
    });
  }
});
