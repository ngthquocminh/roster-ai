import { TableBody, TableCell, TableRow } from "@/components/ui/table";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import type { AssignmentQuery } from "@/api/scenarioProjection";
import { useBaselineAssignments } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { formatMinuteWindow } from "@/lib/formatShiftWindow";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { COLUMNS_BY_GROUP } from "../columns";
import { PaginationControls } from "../PaginationControls";
import { ScenarioDataEmptyRow, ScenarioDataHeader, ScenarioDataTable } from "../ScenarioDataTable";
import type { GroupControls } from "../useGroupControls";

const columns = COLUMNS_BY_GROUP["baseline-assignments"];

export function BaselineAssignmentsPanel({ controls, scenarioId, visibleColumns }: Readonly<{ scenarioId: string; controls?: GroupControls; visibleColumns?: ReadonlySet<string> }>) {
  const query = useBaselineAssignments(scenarioId, (controls?.queryParams ?? {}) as AssignmentQuery);
  const items = query.data?.items ?? [];
  const hasFilters = Object.keys(controls?.activeFilters ?? {}).length > 0;
  const matchingCount = query.data?.matching_count ?? items.length;
  const visible = visibleColumns ?? new Set(columns.map((column) => column.key));
  const renderedColumns = columns.filter((column) => visible.has(column.key));

  return (
    <ScenarioDataGroupState
      columnCount={renderedColumns.length}
      errorStatus={getErrorStatus(query.error)}
      isEmpty={!query.isPending && items.length === 0 && !hasFilters}
      isError={query.isError}
      isPending={query.isPending}
      onRetry={() => {
        void query.refetch();
      }}
    >
      <>
      <ScenarioDataTable caption="Baseline assignments" isBusy={query.isFetching && !query.isPending}>
        <ScenarioDataHeader columns={renderedColumns} onSort={controls?.changeSort ?? (() => undefined)} order={controls?.order ?? "asc"} sort={controls?.sort} />
        <TableBody>
          {hasFilters && matchingCount === 0 ? <ScenarioDataEmptyRow columnCount={renderedColumns.length} /> : null}
          {items.map((item) => (
            <TableRow key={item.record_id}>
              {visible.has("record_id") ? <TableCell><IdentifierCopyButton identifierType="Record ID" value={item.record_id} /></TableCell> : null}
              {visible.has("worker_id") ? <TableCell><IdentifierCopyButton identifierType="Worker ID" value={item.worker_id} /></TableCell> : null}
              {visible.has("task_id") ? <TableCell><IdentifierCopyButton identifierType="Task ID" value={item.task_id} /></TableCell> : null}
              {visible.has("shift_id") ? <TableCell>{item.shift_id ? <IdentifierCopyButton identifierType="Shift ID" value={item.shift_id} /> : "—"}</TableCell> : null}
              {visible.has("window") ? <TableCell>{formatMinuteWindow(item.start_minute, item.end_minute)}</TableCell> : null}
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
      <PaginationControls cursor={controls?.cursor ?? 0} hasFilters={hasFilters} itemCount={items.length} matchingCount={matchingCount} nextCursor={query.data?.next_cursor ?? null} onPageChange={controls?.changePage ?? (() => undefined)} totalCount={query.data?.total_count ?? items.length} />
      </>
    </ScenarioDataGroupState>
  );
}
