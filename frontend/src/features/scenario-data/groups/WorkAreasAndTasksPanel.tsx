import { TableBody, TableCell, TableRow } from "@/components/ui/table";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import type { TaskQuery } from "@/api/scenarioProjection";
import { useWorkAreasAndTasks } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { COLUMNS_BY_GROUP } from "../columns";
import { PaginationControls } from "../PaginationControls";
import { ScenarioDataEmptyRow, ScenarioDataHeader, ScenarioDataTable } from "../ScenarioDataTable";
import type { GroupControls } from "../useGroupControls";

const columns = COLUMNS_BY_GROUP["work-areas-and-tasks"];

export function WorkAreasAndTasksPanel({ controls, scenarioId, visibleColumns }: Readonly<{ scenarioId: string; controls?: GroupControls; visibleColumns?: ReadonlySet<string> }>) {
  const query = useWorkAreasAndTasks(scenarioId, (controls?.queryParams ?? {}) as TaskQuery);
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
      <ScenarioDataTable caption="Work areas and tasks" isBusy={query.isFetching && !query.isPending}>
        <ScenarioDataHeader columns={renderedColumns} onSort={controls?.changeSort ?? (() => undefined)} order={controls?.order ?? "asc"} sort={controls?.sort} />
        <TableBody>
          {hasFilters && matchingCount === 0 ? <ScenarioDataEmptyRow columnCount={renderedColumns.length} /> : null}
          {items.map((item) => (
            <TableRow key={item.record_id}>
              {visible.has("task_id") ? <TableCell><IdentifierCopyButton identifierType="Task ID" value={item.task_id} /></TableCell> : null}
              {visible.has("name") ? <TableCell>{item.name}</TableCell> : null}
              {visible.has("function") ? <TableCell>{item.function}</TableCell> : null}
              {visible.has("area_id") ? <TableCell><IdentifierCopyButton identifierType="Area ID" value={item.area_id} /></TableCell> : null}
              {visible.has("area_name") ? <TableCell>{item.area_name}</TableCell> : null}
              {visible.has("unit_type_id") ? <TableCell className="font-mono text-xs" title={item.unit_type_id ?? "—"}>
                {item.unit_type_id ?? "—"}
              </TableCell> : null}
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
      <PaginationControls cursor={controls?.cursor ?? 0} hasFilters={hasFilters} itemCount={items.length} matchingCount={matchingCount} nextCursor={query.data?.next_cursor ?? null} onPageChange={controls?.changePage ?? (() => undefined)} totalCount={query.data?.total_count ?? items.length} />
      </>
    </ScenarioDataGroupState>
  );
}
