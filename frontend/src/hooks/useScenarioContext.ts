/** Thin TanStack Query wrapper around one immutable scenario context read. */
import { useQuery } from "@tanstack/react-query";

import { getScenarioContext } from "@/api/scenarioCatalogue";


export function useScenarioContext(scenarioId: string) {
  return useQuery({
    queryKey: ["scenario-context", scenarioId] as const,
    queryFn: () => getScenarioContext(scenarioId),
    enabled: Boolean(scenarioId),
  });
}
