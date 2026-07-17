/**
 * CONS-01's apply-constraint write hook. `useMutation` wrapper over
 * `applyConstraint`, following RESEARCH.md Pattern 3.
 *
 * The `["scenario", scenarioId, "overrides"]` invalidation key below MUST
 * stay byte-identical to `useOverrides.ts`'s query key. If the two ever
 * diverge, `POST /constraints` still succeeds and this mutation still
 * reports success — but the overrides list never refetches, so a newly
 * applied constraint silently never appears (T-02-08).
 *
 * Deliberately does NOT invalidate the scenario-detail key
 * (`["scenario", scenarioId]`) — `ScenarioOut` fields never change from
 * `POST /constraints` (RESEARCH.md Open Question 2), so invalidating it
 * would refetch needlessly on every apply.
 *
 * Deliberately no input-clearing or session-log-update behavior lives here
 * either: the resolved `ConstraintParseResponse` is left to propagate to the
 * caller's own `.mutate(text, { onSuccess: (data) => {...} })` callback,
 * because that behavior depends on the *response body* (applied vs.
 * rejected/clarification), not "the request succeeded" — see the input
 * component (plan 02-05).
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { applyConstraint } from "@/api/constraints";

export function useApplyConstraint(scenarioId: string) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (text: string) => applyConstraint({ scenario_id: scenarioId, text }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["scenario", scenarioId, "overrides"] });
    },
  });
}
