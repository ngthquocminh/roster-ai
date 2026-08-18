import { useMutation, useQueryClient } from "@tanstack/react-query";
import { rejectProposal, type ProposalRejection } from "@/api/proposals";
import { proposalKey } from "./useProposal";

export function useRejectProposal(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProposalRejection) => rejectProposal(id, body),
    onSuccess: (proposal) => queryClient.setQueryData(proposalKey(id), proposal),
  });
}
