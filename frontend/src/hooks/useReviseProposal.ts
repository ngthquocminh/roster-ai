import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { reviseProposal, type ProposalRevision } from "@/api/proposals";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";
import { proposalKey } from "./useProposal";

export function useReviseProposal(id: string) {
  const queryClient = useQueryClient();
  // One key per command intent, held across retries. A key minted inside the
  // request function would be new on every attempt, so the server could never
  // recognise a retry and AD-8's replay path would be unreachable from here.
  const keys = useRef(createIdempotencyKeyHolder());
  return useMutation({
    mutationFn: (body: ProposalRevision) =>
      reviseProposal(id, body, keys.current.current()),
    onSuccess: (proposal) => {
      keys.current.settle();
      queryClient.setQueryData(proposalKey(id), proposal);
      // A replayed command answers "what did my command do", so the body just
      // cached can be an old state presented as current (C9). Re-read the truth.
      void queryClient.invalidateQueries({ queryKey: proposalKey(id) });
    },
    onError: () => {
      // Deliberately does NOT settle: the next attempt reuses the same key so a
      // command that succeeded behind a lost response replays instead of
      // colliding on the resource version.
      void queryClient.invalidateQueries({ queryKey: proposalKey(id) });
    },
  });
}
