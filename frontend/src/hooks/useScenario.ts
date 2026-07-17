/**
 * SCEN-03 read hook. Thin `useQuery` wrapper over `getScenario(id)` — single-
 * record variant of `useScenarios.ts`'s list wrapper.
 *
 * The `["scenario", scenarioId]` query key is distinct from `useOverrides.ts`'s
 * `["scenario", scenarioId, "overrides"]` key so the two Editor fetches
 * (scenario detail, overrides list) resolve/error independently (UI-SPEC
 * E1/E2) — this hook is never invalidated by `useApplyConstraint` (RESEARCH
 * Open Question 2: `ScenarioOut` fields never change from `POST /constraints`).
 */
import { useQuery } from "@tanstack/react-query";

import { getScenario } from "@/api/scenarios";

export function useScenario(scenarioId: string) {
  return useQuery({
    queryKey: ["scenario", scenarioId],
    queryFn: () => getScenario(scenarioId),
  });
}
