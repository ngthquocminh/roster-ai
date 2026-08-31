import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { decideApproval, type ApprovalDecision } from "@/api/approvals";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";
import { getErrorStatus } from "@/lib/errors";
import { approvalKey } from "./useApproval";

/**
 * One idempotency key per INTENT, not per panel (AD-8).
 *
 * A transport failure deliberately retains the key so the retry replays rather
 * than issuing a second command. With a single holder shared across approve,
 * reject and dismiss, that retained key was then reused by the *next, different*
 * decision — arriving with a changed body, which the server correctly refuses as
 * `409 idempotency_key_conflict`. Keying the holders by decision keeps "the key
 * identifies one intent" true, which is what `lib/idempotency.ts` promises.
 */
export function useDecideApproval(id: string) {
  const holders = useRef<Record<string, ReturnType<typeof createIdempotencyKeyHolder>>>({});
  const queryClient = useQueryClient();
  const holderFor = (decision: string) => {
    holders.current[decision] ??= createIdempotencyKeyHolder();
    return holders.current[decision];
  };
  return useMutation({
    mutationFn: (body: ApprovalDecision) => decideApproval(id, body, holderFor(body.decision).current()),
    onSettled: (_data, error, variables) => {
      // Settle on any server-acknowledged result, success or refusal: only a
      // transport failure (no status) leaves the key alive for an honest retry.
      if (!error || getErrorStatus(error) !== undefined) holderFor(variables.decision).settle();
      void queryClient.invalidateQueries({ queryKey: approvalKey(id) });
      void queryClient.invalidateQueries({ queryKey: ["run-approvals"] });
      void queryClient.invalidateQueries({ queryKey: ["conversation-timeline"] });
      void queryClient.invalidateQueries({ queryKey: ["scheduleRunResult"] });
      void queryClient.invalidateQueries({ queryKey: ["scenario-projection"] });
    },
  });
}
