/**
 * RUN-01's trigger-run write hook. `useMutation` wrapper over `triggerRun`,
 * following the same shape as `useCreateScenario.ts`.
 *
 * The `["runs", scenarioId]` invalidation key below MUST stay byte-identical
 * to `useRuns.ts`'s query key. If the two ever diverge, `POST
 * /scenarios/{id}/runs` still succeeds and this mutation still reports
 * success — but the list never refetches, so the new `PENDING` run silently
 * never appears before the next poll tick.
 *
 * Deliberately no other cache write or clearing on success: the caller reads
 * the returned `RunOut` directly, and the invalidation alone is what makes
 * RUN-01's "appear immediately" true.
 *
 * The mutation's error (with its HTTP `status` attached by `triggerRun`) is
 * left to propagate untouched to the caller so it can branch on 404 vs other
 * failures.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { triggerRun } from "@/api/runs";

export function useTriggerRun(scenarioId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => triggerRun(scenarioId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["runs", scenarioId] });
    },
  });
}
