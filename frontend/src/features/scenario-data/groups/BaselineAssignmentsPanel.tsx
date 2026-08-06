import { TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useBaselineAssignments } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { formatMinuteWindow } from "@/lib/formatShiftWindow";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { ScenarioDataTable } from "../ScenarioDataTable";

const headers = ["Record ID", "Worker ID", "Task ID", "Shift ID", "Window"];

export function BaselineAssignmentsPanel({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const query = useBaselineAssignments(scenarioId);
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
      <ScenarioDataTable caption="Baseline assignments">
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
              <TableCell className="font-mono text-xs" title={item.worker_id}>
                {item.worker_id}
              </TableCell>
              <TableCell className="font-mono text-xs" title={item.task_id}>
                {item.task_id}
              </TableCell>
              <TableCell className="font-mono text-xs" title={item.shift_id ?? "—"}>
                {item.shift_id ?? "—"}
              </TableCell>
              <TableCell>{formatMinuteWindow(item.start_minute, item.end_minute)}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
    </ScenarioDataGroupState>
  );
}
