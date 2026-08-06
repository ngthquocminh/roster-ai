import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useConstraintsAndObjectives } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { ScenarioDataTable } from "../ScenarioDataTable";

const headers = ["Record ID", "Constraint type", "Value", "Value type"];

export function ConstraintsPanel({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const query = useConstraintsAndObjectives(scenarioId);
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
      <ScenarioDataTable caption="Constraints and objectives">
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
              <TableCell>{item.constraint_type}</TableCell>
              <TableCell>{item.value}</TableCell>
              <TableCell>{item.value_type ?? "—"}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
    </ScenarioDataGroupState>
  );
}
