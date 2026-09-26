/** TanStack Query ownership for direct, immutable scenario projection reads. */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import {
  getBaselineAssignments,
  getConstraintsAndObjectives,
  getDemand,
  getLocks,
  getScenarioOverview,
  getWorkAreasAndTasks,
  getWorkers,
  type AssignmentQuery,
  type ConstraintQuery,
  type DemandQuery,
  type LockQuery,
  type TaskQuery,
  type WorkerQuery,
} from "@/api/scenarioProjection";
import { useRedirectOnUnauthorized } from "@/hooks/useRedirectOnUnauthorized";
import { getErrorStatus } from "@/lib/errors";

// Deliberately no staleTime: each scenario_version is immutable, but the API
// re-resolves the latest imported version and must refetch after a re-import.
//
// Each group query can 401 independently of the parent scenario-context
// query one route level up, so every group hook redirects on its own —
// mirrors the pattern ScenarioWorkspace/FixtureCatalogue use for theirs.
function useProjectionQuery<T>(
  queryKey: readonly unknown[],
  queryFn: () => Promise<T>,
  scenarioId: string,
  preservePrevious = false,
) {
  const query = useQuery({
    queryKey,
    queryFn,
    enabled: Boolean(scenarioId),
    retry: false,
    placeholderData: preservePrevious ? keepPreviousData : undefined,
  });
  useRedirectOnUnauthorized(getErrorStatus(query.error));
  return query;
}

export function useScenarioOverview(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "overview"],
    () => getScenarioOverview(scenarioId),
    scenarioId,
  );
}

export function useWorkAreasAndTasks(scenarioId: string, params: TaskQuery = {}) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "work-areas-and-tasks", params],
    () => getWorkAreasAndTasks(scenarioId, params),
    scenarioId,
    true,
  );
}

export function useWorkers(scenarioId: string, params: WorkerQuery = {}) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "workers", params],
    () => getWorkers(scenarioId, params),
    scenarioId,
    true,
  );
}

// Assignments carry only worker/task IDs (per docs/DOMAIN-MODEL.md); the UI resolves display
// names by paging through every worker/task once and keying the result by the same business
// ID assignments reference (contact_id, task_id) — not the projection record_id.
const NAME_PAGE_LIMIT = 200;

export function useWorkerNameMap(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "workers", "name-map"],
    async () => {
      const map = new Map<string, string>();
      let cursor: number | undefined = 0;
      while (cursor !== undefined) {
        const page = await getWorkers(scenarioId, { cursor, limit: NAME_PAGE_LIMIT });
        for (const item of page.items) map.set(item.contact_id, item.name);
        cursor = page.next_cursor ?? undefined;
      }
      return map;
    },
    scenarioId,
  );
}

export function useTaskNameMap(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "work-areas-and-tasks", "name-map"],
    async () => {
      const map = new Map<string, string>();
      let cursor: number | undefined = 0;
      while (cursor !== undefined) {
        const page = await getWorkAreasAndTasks(scenarioId, { cursor, limit: NAME_PAGE_LIMIT });
        for (const item of page.items) map.set(item.task_id, item.name);
        cursor = page.next_cursor ?? undefined;
      }
      return map;
    },
    scenarioId,
  );
}

export function useDemand(scenarioId: string, params: DemandQuery = {}) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "demand", params],
    () => getDemand(scenarioId, params),
    scenarioId,
    true,
  );
}

export function useBaselineAssignments(scenarioId: string, params: AssignmentQuery = {}) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "baseline-assignments", params],
    () => getBaselineAssignments(scenarioId, params),
    scenarioId,
    true,
  );
}

export function useLocks(scenarioId: string, params: LockQuery = {}) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "locks", params],
    () => getLocks(scenarioId, params),
    scenarioId,
    true,
  );
}

export function useConstraintsAndObjectives(scenarioId: string, params: ConstraintQuery = {}) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "constraints-and-objectives", params],
    () => getConstraintsAndObjectives(scenarioId, params),
    scenarioId,
    true,
  );
}
