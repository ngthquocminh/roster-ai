import { TableBody, TableCell, TableRow } from "@/components/ui/table";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import type { WorkerQuery } from "@/api/scenarioProjection";
import { useWorkers } from "@/hooks/useScenarioProjection";
import { formatMinuteWindow } from "@/lib/formatShiftWindow";
import { getErrorStatus } from "@/lib/errors";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { COLUMNS_BY_GROUP } from "../columns";
import { PaginationControls } from "../PaginationControls";
import { ScenarioDataEmptyRow, ScenarioDataHeader, ScenarioDataTable } from "../ScenarioDataTable";
import type { GroupControls } from "../useGroupControls";

const columns = COLUMNS_BY_GROUP.workers;

export function WorkersPanel({ controls, scenarioId, visibleColumns }: Readonly<{ scenarioId: string; controls?: GroupControls; visibleColumns?: ReadonlySet<string> }>) {
  const query = useWorkers(scenarioId, (controls?.queryParams ?? {}) as WorkerQuery);
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
      <ScenarioDataTable caption="Workers" isBusy={query.isFetching && !query.isPending}>
        <ScenarioDataHeader columns={renderedColumns} onSort={controls?.changeSort ?? (() => undefined)} order={controls?.order ?? "asc"} sort={controls?.sort} />
        <TableBody>
          {hasFilters && matchingCount === 0 ? <ScenarioDataEmptyRow columnCount={renderedColumns.length} /> : null}
          {items.map((item) => (
            <TableRow key={item.record_id}>
              {visible.has("contact_id") ? <TableCell><IdentifierCopyButton identifierType="Contact ID" value={item.contact_id} /></TableCell> : null}
              {visible.has("name") ? <TableCell>{item.name}</TableCell> : null}
              {visible.has("employment_type") ? <TableCell>{item.employment_type}</TableCell> : null}
              {visible.has("grade") ? <TableCell>{item.grade}</TableCell> : null}
              {visible.has("eba") ? <TableCell>{item.eba}</TableCell> : null}
              {visible.has("contracted_hours") ? <TableCell>{item.contracted_hours}</TableCell> : null}
              {visible.has("qualifications") ? <TableCell>
                {item.qualifications.length
                  ? item.qualifications.map((q) => `${q.task_id} (${q.rate})`).join(", ")
                  : "—"}
              </TableCell> : null}
              {visible.has("availability_windows") ? <TableCell>
                {item.availability_windows.length
                  ? item.availability_windows
                      .map((w) => `${w.kind} ${formatMinuteWindow(w.start_minute, w.end_minute)}`)
                      .join("; ")
                  : "—"}
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
