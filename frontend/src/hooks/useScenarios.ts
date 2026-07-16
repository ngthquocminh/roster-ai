/**
 * SCEN-01 read hook. Thin `useQuery` wrapper over `listScenarios` — no
 * transformation of the response happens here or anywhere downstream: the
 * backend returns scenarios newest-first (`docs/API.md`) and owns that
 * ordering exclusively.
 *
 * The `["scenarios"]` query key is a cross-plan contract: plan 01-07's
 * create-scenario mutation invalidates this exact key so a newly created
 * scenario appears without a manual refetch. If the two keys ever diverge,
 * creation succeeds silently and the new row never appears.
 *
 * No background-polling option is set here — polling is Phase 3's need (run
 * status), not this list's; a background poll here would be invented
 * behaviour with a real cost and no requirement behind it.
 */
import { useQuery } from "@tanstack/react-query";

import { listScenarios } from "@/api/scenarios";

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: listScenarios,
  });
}
