import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useWorkAreasAndTasks } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { ScenarioDataTable } from "../ScenarioDataTable";

const headers = ["Task ID", "Name", "Function", "Area ID", "Area name", "Unit type ID"];

export function WorkAreasAndTasksPanel({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const query = useWorkAreasAndTasks(scenarioId);
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
      <ScenarioDataTable caption="Work areas and tasks">
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
              <TableCell className="font-mono text-xs" title={item.task_id}>
                {item.task_id}
              </TableCell>
              <TableCell>{item.name}</TableCell>
              <TableCell>{item.function}</TableCell>
              <TableCell className="font-mono text-xs" title={item.area_id}>
                {item.area_id}
              </TableCell>
              <TableCell>{item.area_name}</TableCell>
              <TableCell className="font-mono text-xs" title={item.unit_type_id ?? "—"}>
                {item.unit_type_id ?? "—"}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
    </ScenarioDataGroupState>
  );
}
