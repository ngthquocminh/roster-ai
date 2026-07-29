/** Thin TanStack Query wrapper around one immutable scenario context read. */
import { useQuery } from "@tanstack/react-query";

import { getScenarioContext } from "@/api/scenarioCatalogue";


export function useScenarioContext(scenarioId: string) {
  return useQuery({
    queryKey: ["scenario-context", scenarioId] as const,
    queryFn: () => getScenarioContext(scenarioId),
    enabled: Boolean(scenarioId),
    // See useFixtureCatalogue: terminal statuses must not be retried, and no
    // staleTime — `baseline_schedule_version` is null today but Epic 3/4 will
    // populate it, and suppressing background refetches would also make the
    // stale-context state unreachable.
    retry: false,
  });
}
