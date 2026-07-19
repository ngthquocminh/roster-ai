/**
 * D-12's deep-link status probe. Thin `useQuery` wrapper over `getRun(id)` —
 * the first, ungated fetch in the Results dependent-query chain (mirrors
 * `useScenario.ts`'s ungated shape). Always resolves regardless of run
 * status, so it never 409s the way `GET /runs/{run_id}/result` can — this is
 * what `useRunResult.ts`'s `enabled` gate reads (`status === "COMPLETED"`)
 * before ever calling that endpoint.
 *
 * The `["run", runId]` query key is a prefix of `useRunResult.ts`'s
 * `["run", runId, "result"]` key — intentional TanStack Query key hierarchy
 * convention (mirrors `["scenario", scenarioId]` /
 * `["scenario", scenarioId, "overrides"]` in `useScenario.ts`/`useOverrides.ts`).
 */
import { useQuery } from "@tanstack/react-query";

import { getRun } from "@/api/runs";

export function useRun(runId: string) {
  return useQuery({
    queryKey: ["run", runId],
    queryFn: () => getRun(runId),
  });
}
