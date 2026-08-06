import { useMemo } from "react";
import { useSearchParams } from "react-router";

import { COLUMNS_BY_GROUP, type ScenarioDataListGroup } from "./columns";
import { FILTERS_BY_GROUP } from "./filters";
import { PAGE_SIZE } from "./PaginationControls";

export function useGroupControls(group: ScenarioDataListGroup) {
  const [searchParams, setSearchParams] = useSearchParams();
  const columns = COLUMNS_BY_GROUP[group];
  const filters = FILTERS_BY_GROUP[group];
  const sortKeys = new Set(columns.flatMap((column) => column.sortKey ? [column.sortKey] : []));
  const requestedSort = searchParams.get("sort") ?? undefined;
  const sort = requestedSort && sortKeys.has(requestedSort) ? requestedSort : undefined;
  const requestedOrder = searchParams.get("order");
  const order: "asc" | "desc" = requestedOrder === "desc" ? "desc" : "asc";
  const requestedCursor = Number(searchParams.get("cursor") ?? 0);
  const cursor = Number.isInteger(requestedCursor) && requestedCursor >= 0 ? requestedCursor : 0;
  // react-router memoizes `searchParams` on `location.search`, so it (and `filters`, a per-group
  // module constant) are stable across unrelated re-renders — memoizing on them keeps this object's
  // identity stable too, so FilterBar's draft-resync effect doesn't fire when nothing here changed.
  const activeFilters = useMemo(
    () =>
      Object.fromEntries(
        filters.flatMap((filter) => {
          const value = searchParams.get(filter.param);
          if (value === null || value === "") return [];
          if (filter.kind === "number" && !Number.isFinite(Number(value))) return [];
          return [[filter.param, value]];
        }),
      ),
    [searchParams, filters],
  );

  const update = (mutate: (next: URLSearchParams) => void) => {
    const next = new URLSearchParams(searchParams);
    mutate(next);
    setSearchParams(next);
  };
  const resetCursor = (next: URLSearchParams) => next.delete("cursor");

  const applyFilters = (values: Record<string, string>) => update((next) => {
    for (const filter of filters) next.delete(filter.param);
    for (const filter of filters) {
      const value = values[filter.param]?.trim();
      if (value) next.set(filter.param, value);
    }
    resetCursor(next);
  });
  const clearFilters = () => update((next) => {
    for (const filter of filters) next.delete(filter.param);
    resetCursor(next);
  });
  const removeFilter = (param: string) => update((next) => {
    next.delete(param);
    resetCursor(next);
  });
  const changeSort = (sortKey: string) => update((next) => {
    const nextOrder = sort === sortKey && order === "asc" ? "desc" : "asc";
    next.set("sort", sortKey);
    next.set("order", nextOrder);
    resetCursor(next);
  });
  const changePage = (nextCursor: number) => update((next) => {
    if (nextCursor === 0) next.delete("cursor");
    else next.set("cursor", String(nextCursor));
  });
  const changeGroup = (nextGroup: string) => setSearchParams({ group: nextGroup });

  const queryParams: Record<string, string | number | undefined> = {
    cursor,
    limit: PAGE_SIZE,
    sort,
    order,
  };
  for (const filter of filters) {
    const value = activeFilters[filter.param];
    if (value !== undefined) queryParams[filter.param] = filter.kind === "number" ? Number(value) : value;
  }

  return {
    activeFilters,
    applyFilters,
    changeGroup,
    changePage,
    changeSort,
    clearFilters,
    cursor,
    order,
    queryParams,
    removeFilter,
    sort,
  };
}

export type GroupControls = ReturnType<typeof useGroupControls>;
