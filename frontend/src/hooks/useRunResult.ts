/**
 * RES-01..RES-03 read hook for the run result — a dependent query
 * (RESEARCH.md Pattern 1) gated by `options.enabled`, mirroring
 * `useOverrides.ts`'s exact `enabled` gating shape. The caller (ResultsView,
 * plan 04-07) passes `runQuery.data?.status === "COMPLETED"`, so this hook
 * NEVER calls `getRunResult` before the run is COMPLETED — that is the
 * mechanism that keeps `GET /runs/{run_id}/result` from ever hitting its
 * pre-COMPLETED 409 (D-12). Callers must not work around the gate with a
 * try/catch on the 409; wire `enabled` correctly instead.
 *
 * The `["run", runId, "result"]` query key is a prefix-extension of
 * `useRun.ts`'s `["run", runId]` key (mirrors
 * `["scenario", scenarioId]` / `["scenario", scenarioId, "overrides"]` in
 * `useScenario.ts`/`useOverrides.ts`).
 */
import { useQuery } from "@tanstack/react-query";

import { getRunResult } from "@/api/results";

export function useRunResult(runId: string, options: { enabled: boolean }) {
  return useQuery({
    queryKey: ["run", runId, "result"],
    queryFn: () => getRunResult(runId),
    enabled: options.enabled,
  });
}
