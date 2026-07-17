/**
 * SCEN-03 read hook for the overrides list — a dependent query (RESEARCH
 * Pattern 3) gated by `options.enabled` (caller passes
 * `scenarioQuery.isSuccess`) so this never fires an independent 404 for a
 * scenario that hasn't resolved yet (T-02-09).
 *
 * Cross-file query-key contract (same hazard `useScenarios.ts`'s own header
 * comment documents for `["scenarios"]`): this exact query key
 * (`["scenario", scenarioId, "overrides"]`) MUST byte-match the key
 * `useApplyConstraint.ts` invalidates on a successful apply. If the two ever
 * diverge, applying a constraint succeeds but the overrides list silently
 * never refetches (T-02-08).
 */
import { useQuery } from "@tanstack/react-query";

import { getScenarioOverrides } from "@/api/scenarios";

export function useOverrides(scenarioId: string, options: { enabled: boolean }) {
  return useQuery({
    queryKey: ["scenario", scenarioId, "overrides"],
    queryFn: () => getScenarioOverrides(scenarioId),
    enabled: options.enabled,
  });
}
