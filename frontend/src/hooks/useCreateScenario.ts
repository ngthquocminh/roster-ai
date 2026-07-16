/**
 * SCEN-02's create-scenario write hook. `useMutation` wrapper over
 * `createScenario`, following RESEARCH.md Pattern 3.
 *
 * The `["scenarios"]` invalidation key below MUST stay byte-identical to
 * `useScenarios.ts`'s query key. If the two ever diverge, `POST /scenarios`
 * still succeeds and this mutation still reports success — but the list
 * never refetches, so the new row silently never appears. That reads as a
 * backend bug and is not one.
 *
 * Deliberately no optimistic mutation lifecycle hook or manual cache write:
 * the `["scenarios"]` cache is left untouched until the server confirms and
 * the invalidated query refetches. An optimistic insert would show a row the
 * backend has never heard of; if the POST then failed, the rollback would be
 * a row vanishing for reasons the user cannot connect to anything.
 *
 * The mutation's error (with its HTTP `status` attached by `createScenario`,
 * plan 01-04) is left to propagate to the caller — `CreateScenarioDialog`
 * needs it intact to choose between the 400 and 422 inline messages.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createScenario } from "@/api/scenarios";

export function useCreateScenario() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createScenario,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenarios"] });
    },
  });
}
