/**
 * RUN-02 self-terminating polling list hook. Thin `useQuery` wrapper over
 * `listRuns` — no transformation of the response happens here: the run list
 * is rendered in whatever order the backend returns it.
 *
 * `refetchInterval` is a predicate driven by `hasActiveRun` (`@/lib/runStatus`)
 * — the exact same function the in-flight panel and table use to decide
 * "still running": while the fetched list has any non-terminal run it returns
 * the fixed poll cadence, and the instant every run is terminal (or the list
 * is empty) it returns `false`. React Query owns the interval's lifecycle —
 * it clears the timer on unmount and whenever the predicate flips to
 * `false` — so no manual timer bookkeeping lives here.
 *
 * The `["runs", scenarioId]` query key is a cross-plan contract: this same
 * plan's `useTriggerRun` invalidates this exact key on a successful trigger
 * so the new run appears without waiting for the next tick. If the two keys
 * ever diverge, a triggered run silently never shows up.
 */
import { useQuery } from "@tanstack/react-query";

import { listRuns } from "@/api/runs";
import { hasActiveRun } from "@/lib/runStatus";

const RUNS_POLL_INTERVAL_MS = 2000;

export function useRuns(scenarioId: string) {
  return useQuery({
    queryKey: ["runs", scenarioId],
    queryFn: () => listRuns(scenarioId),
    refetchInterval: (query) =>
      hasActiveRun(query.state.data ?? []) ? RUNS_POLL_INTERVAL_MS : false,
  });
}
