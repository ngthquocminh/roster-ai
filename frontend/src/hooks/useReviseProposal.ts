import { useMutation, useQueryClient } from "@tanstack/react-query";
import { reviseProposal, type ProposalRevision } from "@/api/proposals";
import { proposalKey } from "./useProposal";

export function useReviseProposal(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ProposalRevision) => reviseProposal(id, body),
    onSuccess: (proposal) => queryClient.setQueryData(proposalKey(id), proposal),
  });
}
