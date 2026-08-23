/** TanStack Query ownership for the Runs workspace list (Story 3.7 AC1). */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { listScheduleRuns } from "@/api/scheduleRuns";
import { useRedirectOnUnauthorized } from "@/hooks/useRedirectOnUnauthorized";
import { getErrorStatus } from "@/lib/errors";

/** The one place this cache key is spelled. `useCancelScheduleRun` and
 * `useStartScheduleRun` invalidate the bare prefix, so a rename here cannot
 * silently stop matching them — the codebase's convention (`proposalKey`,
 * `conversationTimelineKey`) is an exported factory, not literals in each
 * caller. */
export const scheduleRunsKey = (scenarioId?: string, cursor?: number) =>
  scenarioId === undefined
    ? (["scheduleRuns"] as const)
    : (["scheduleRuns", scenarioId, cursor] as const);

export function useScheduleRuns(scenarioId: string, cursor = 0) {
  const query = useQuery({
    queryKey: scheduleRunsKey(scenarioId, cursor),
    queryFn: () => listScheduleRuns({ scenario_id: scenarioId, cursor }),
    enabled: Boolean(scenarioId),
    retry: false,
    // Paging changes the query key, so without this the table is torn down to
    // skeletons on every page turn — and the Next button the planner just
    // pressed evaluates to `disabled` mid-fetch, dropping keyboard focus to
    // <body>. Keeping the previous page rendered makes paging happen in place.
    placeholderData: keepPreviousData,
  });
  useRedirectOnUnauthorized(getErrorStatus(query.error));
  return query;
}
