import { useQuery } from "@tanstack/react-query";
import { getProposal } from "@/api/proposals";

export const proposalKey = (id: string) => ["proposal", id] as const;

export function useProposal(id: string) {
  return useQuery({
    queryKey: proposalKey(id),
    queryFn: () => getProposal(id),
    enabled: Boolean(id),
    retry: false,
  });
}
