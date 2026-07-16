/**
 * SCEN-02's fixture-picklist read hook (D-03: the fixture picklist IS the
 * reason v0.4 has no path for introducing new input files). Thin `useQuery`
 * wrapper over `listFixtures`, following RESEARCH.md Pattern 3 — no
 * transformation of the response happens here.
 */
import { useQuery } from "@tanstack/react-query";

import { listFixtures } from "@/api/scenarios";

export function useFixtures() {
  return useQuery({
    queryKey: ["fixtures"],
    queryFn: listFixtures,
  });
}
