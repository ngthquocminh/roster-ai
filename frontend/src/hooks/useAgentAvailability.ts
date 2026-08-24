import { useQuery } from "@tanstack/react-query";

import { getAgentAvailability } from "@/api/agentAvailability";

export const agentAvailabilityKey = (scenarioId: string) =>
  ["agent-availability", scenarioId] as const;

export function useAgentAvailability(scenarioId: string) {
  return useQuery({
    queryKey: agentAvailabilityKey(scenarioId),
    queryFn: () => getAgentAvailability(scenarioId),
    enabled: Boolean(scenarioId),
    retry: false,
  });
}
