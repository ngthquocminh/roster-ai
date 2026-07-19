/**
 * RES-04/RES-05's button-triggered insight fetch (D-11). `useMutation`
 * wrapper over `getRunInsights`, adapted from `useTriggerRun.ts` but
 * deliberately WITHOUT its cache-writing `onSuccess` step: no other query
 * depends on insight-fetch completion, and RES-05 requires this fetch be
 * structurally isolated from the run/result query cache — a 502 here must
 * never write to or clear `['run', ...]`, so the rest of the completed
 * schedule stays rendered and untouched. This hook intentionally has no
 * access to the app's shared cache object at all.
 *
 * `useMutation` (not `useQuery` + `enabled: false` + manual `refetch()`) is
 * used because it gives `isIdle`/`isPending`/`isError`/`error`/`data`/
 * `mutate()` retry semantics for free — exactly the shape D-13's retry
 * affordance needs, matching how `useTriggerRun` already models a
 * user-triggered network call in this codebase.
 */
import { useMutation } from "@tanstack/react-query";

import { getRunInsights } from "@/api/insights";

export function useRunInsights(runId: string) {
  return useMutation({
    mutationFn: () => getRunInsights(runId),
  });
}
