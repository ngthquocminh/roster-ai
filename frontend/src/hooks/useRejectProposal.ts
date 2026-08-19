import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { rejectProposal, type ProposalRejection } from "@/api/proposals";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";
import { proposalKey } from "./useProposal";

export function useRejectProposal(id: string) {
  const queryClient = useQueryClient();
  // See useReviseProposal: the key is held across retries so a rejection whose
  // response was lost replays rather than being refused as stale.
  const keys = useRef(createIdempotencyKeyHolder());
  return useMutation({
    mutationFn: (body: ProposalRejection) =>
      rejectProposal(id, body, keys.current.current()),
    onSuccess: (proposal) => {
      keys.current.settle();
      queryClient.setQueryData(proposalKey(id), proposal);
    },
    onError: () => {
      void queryClient.invalidateQueries({ queryKey: proposalKey(id) });
    },
  });
}
