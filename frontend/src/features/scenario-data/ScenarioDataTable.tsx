import type { ReactNode } from "react";

import { Table, TableCaption } from "@/components/ui/table";

export function ScenarioDataTable({ caption, children }: Readonly<{ caption: string; children: ReactNode }>) {
  return (
    <div aria-label={caption} className="max-h-[65vh] overflow-auto rounded-md border [&_[data-slot=table-container]]:overflow-visible" role="region" tabIndex={0}>
      <Table className="min-w-max [&_thead]:sticky [&_thead]:top-0 [&_thead]:z-10 [&_thead]:bg-muted">
        <TableCaption className="sr-only">{caption}</TableCaption>
        {children}
      </Table>
    </div>
  );
}
