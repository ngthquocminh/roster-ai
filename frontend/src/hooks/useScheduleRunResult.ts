import { useQuery } from "@tanstack/react-query";

import { getScheduleRunResult } from "@/api/scheduleRuns";
import { useRedirectOnUnauthorized } from "@/hooks/useRedirectOnUnauthorized";
import { getErrorStatus } from "@/lib/errors";

export const scheduleRunResultKey = (runId: string) =>
  ["scheduleRunResult", runId] as const;

export function useScheduleRunResult(runId: string) {
  const query = useQuery({
    queryKey: scheduleRunResultKey(runId),
    queryFn: () => getScheduleRunResult(runId),
    enabled: Boolean(runId),
    retry: false,
  });
  useRedirectOnUnauthorized(getErrorStatus(query.error));
  return query;
}
