/** TanStack Query ownership for the Runs workspace list (Story 3.7 AC1). */
import { useQuery } from "@tanstack/react-query";

import { listScheduleRuns } from "@/api/scheduleRuns";
import { useRedirectOnUnauthorized } from "@/hooks/useRedirectOnUnauthorized";
import { getErrorStatus } from "@/lib/errors";

export function useScheduleRuns(scenarioId: string, cursor = 0) {
  const query = useQuery({
    queryKey: ["scheduleRuns", scenarioId, cursor],
    queryFn: () => listScheduleRuns({ scenario_id: scenarioId, cursor }),
    enabled: Boolean(scenarioId),
    retry: false,
  });
  useRedirectOnUnauthorized(getErrorStatus(query.error));
  return query;
}
