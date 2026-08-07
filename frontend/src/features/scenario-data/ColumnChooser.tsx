import { Columns3 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuCheckboxItem, DropdownMenuContent, DropdownMenuLabel, DropdownMenuSeparator, DropdownMenuTrigger } from "@/components/ui/dropdown-menu";
import type { ColumnDef } from "./columns";

export function ColumnChooser({ columns, onVisibilityChange, revealedField, visibleKeys }: Readonly<{
  columns: readonly ColumnDef[];
  visibleKeys: ReadonlySet<string>;
  revealedField?: string;
  onVisibilityChange: (key: string, visible: boolean) => void;
}>) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild><Button className="min-h-11" type="button" variant="outline"><Columns3 aria-hidden="true" />Choose columns</Button></DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuLabel>Visible columns</DropdownMenuLabel>
        <DropdownMenuSeparator />
        {columns.map((column) => {
          const revealed = column.key === revealedField;
          return (
            <DropdownMenuCheckboxItem checked={visibleKeys.has(column.key)} className="min-h-11" disabled={column.required || revealed} key={column.key} onCheckedChange={(checked) => onVisibilityChange(column.key, checked === true)} onSelect={(event) => event.preventDefault()}>
              <span className="grid gap-0.5"><span>{column.header}</span>{revealed ? <span className="text-xs text-muted-foreground">Shown for the linked evidence target.</span> : null}</span>
            </DropdownMenuCheckboxItem>
          );
        })}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
