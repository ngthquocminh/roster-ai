import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useLocks } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { ScenarioDataTable } from "../ScenarioDataTable";

const headers = ["Record ID", "Target type", "Target ref", "Scope", "Source"];

export function LocksPanel({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const query = useLocks(scenarioId);
  const items = query.data?.items ?? [];

  return (
    <ScenarioDataGroupState
      columnCount={headers.length}
      errorStatus={getErrorStatus(query.error)}
      isEmpty={!query.isPending && items.length === 0}
      isError={query.isError}
      isPending={query.isPending}
      onRetry={() => {
        void query.refetch();
      }}
    >
      <ScenarioDataTable caption="Locks">
        <TableHeader>
          <TableRow>
            {headers.map((header) => (
              <TableHead key={header} scope="col">
                {header}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {items.map((item) => (
            <TableRow key={item.record_id}>
              <TableCell className="font-mono text-xs" title={item.record_id}>
                {item.record_id}
              </TableCell>
              <TableCell>{item.target_type}</TableCell>
              <TableCell className="font-mono text-xs" title={item.target_ref}>
                {item.target_ref}
              </TableCell>
              <TableCell>{item.scope}</TableCell>
              <TableCell>{item.source}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
    </ScenarioDataGroupState>
  );
}
