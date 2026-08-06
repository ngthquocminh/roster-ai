import type { ReactNode } from "react";

import { Table, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";
import type { ColumnDef } from "./columns";

export function ScenarioDataHeader({ columns, onSort, order, sort }: Readonly<{
  columns: readonly ColumnDef[];
  sort?: string;
  order: "asc" | "desc";
  onSort: (sortKey: string) => void;
}>) {
  return (
    <TableHeader>
      <TableRow>
        {columns.map((column) => column.sortKey ? (
          <TableHead aria-label={column.header} aria-sort={sort === column.sortKey ? (order === "asc" ? "ascending" : "descending") : "none"} key={column.key} scope="col">
            <button aria-label={`Sort by ${column.header}`} className="min-h-11" onClick={() => onSort(column.sortKey!)} type="button">{column.header}</button>
          </TableHead>
        ) : <TableHead key={column.key} scope="col">{column.header}</TableHead>)}
      </TableRow>
    </TableHeader>
  );
}

export function ScenarioDataEmptyRow({ columnCount }: Readonly<{ columnCount: number }>) {
  return <TableRow><TableCell colSpan={columnCount}>No records in this group match these filters.</TableCell></TableRow>;
}

export function ScenarioDataTable({ caption, children, isBusy = false }: Readonly<{ caption: string; children: ReactNode; isBusy?: boolean }>) {
  return (
    <div aria-busy={isBusy || undefined} aria-label={caption} className={cn("max-h-[65vh] overflow-auto rounded-md border [&_[data-slot=table-container]]:overflow-visible", isBusy && "opacity-60")} role="region" tabIndex={0}>
      <Table className="min-w-max [&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 [&_thead]:bg-muted">
        <TableCaption className="sr-only">{caption}</TableCaption>
        {children}
      </Table>
    </div>
  );
}
