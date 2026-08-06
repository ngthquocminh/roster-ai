import { TableBody, TableCell, TableRow } from "@/components/ui/table";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import type { ConstraintQuery } from "@/api/scenarioProjection";
import { useConstraintsAndObjectives } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { COLUMNS_BY_GROUP } from "../columns";
import { PaginationControls } from "../PaginationControls";
import { ScenarioDataEmptyRow, ScenarioDataHeader, ScenarioDataTable } from "../ScenarioDataTable";
import type { GroupControls } from "../useGroupControls";

const columns = COLUMNS_BY_GROUP["constraints-and-objectives"];

export function ConstraintsPanel({ controls, scenarioId, visibleColumns }: Readonly<{ scenarioId: string; controls?: GroupControls; visibleColumns?: ReadonlySet<string> }>) {
  const query = useConstraintsAndObjectives(scenarioId, (controls?.queryParams ?? {}) as ConstraintQuery);
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
      <ScenarioDataTable caption="Constraints and objectives" isBusy={query.isFetching && !query.isPending}>
        <ScenarioDataHeader columns={renderedColumns} onSort={controls?.changeSort ?? (() => undefined)} order={controls?.order ?? "asc"} sort={controls?.sort} />
        <TableBody>
          {hasFilters && matchingCount === 0 ? <ScenarioDataEmptyRow columnCount={renderedColumns.length} /> : null}
          {items.map((item) => (
            <TableRow key={item.record_id}>
              {visible.has("record_id") ? <TableCell><IdentifierCopyButton identifierType="Record ID" value={item.record_id} /></TableCell> : null}
              {visible.has("constraint_type") ? <TableCell>{item.constraint_type}</TableCell> : null}
              {visible.has("value") ? <TableCell>{item.value}</TableCell> : null}
              {visible.has("value_type") ? <TableCell>{item.value_type ?? "—"}</TableCell> : null}
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
      <PaginationControls cursor={controls?.cursor ?? 0} hasFilters={hasFilters} itemCount={items.length} matchingCount={matchingCount} nextCursor={query.data?.next_cursor ?? null} onPageChange={controls?.changePage ?? (() => undefined)} totalCount={query.data?.total_count ?? items.length} />
      </>
    </ScenarioDataGroupState>
  );
}
