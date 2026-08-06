/** TanStack Query ownership for direct, immutable scenario projection reads. */
import { useQuery } from "@tanstack/react-query";

import {
  getBaselineAssignments,
  getConstraintsAndObjectives,
  getDemand,
  getLocks,
  getScenarioOverview,
  getWorkAreasAndTasks,
  getWorkers,
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
) {
  const query = useQuery({
    queryKey,
    queryFn,
    enabled: Boolean(scenarioId),
    retry: false,
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

export function useWorkAreasAndTasks(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "work-areas-and-tasks"],
    () => getWorkAreasAndTasks(scenarioId),
    scenarioId,
  );
}

export function useWorkers(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "workers"],
    () => getWorkers(scenarioId),
    scenarioId,
  );
}

export function useDemand(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "demand"],
    () => getDemand(scenarioId),
    scenarioId,
  );
}

export function useBaselineAssignments(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "baseline-assignments"],
    () => getBaselineAssignments(scenarioId),
    scenarioId,
  );
}

export function useLocks(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "locks"],
    () => getLocks(scenarioId),
    scenarioId,
  );
}

export function useConstraintsAndObjectives(scenarioId: string) {
  return useProjectionQuery(
    ["scenario-projection", scenarioId, "constraints-and-objectives"],
    () => getConstraintsAndObjectives(scenarioId),
    scenarioId,
  );
}
