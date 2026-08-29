import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { requestApproval, type ApprovalRequest } from "@/api/approvals";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";
import { getErrorStatus } from "@/lib/errors";

export function useRequestApproval() {
  const keys = useRef(createIdempotencyKeyHolder());
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApprovalRequest) => requestApproval(body, keys.current.current()),
    onSuccess: () => { keys.current.settle(); void queryClient.invalidateQueries({ queryKey: ["run-approvals"] }); },
    onError: (error) => {
      // Settle on a SERVER-ANSWERED failure, and only then.
      //
      // Holding the key across retries is deliberate (see `idempotency.ts`): it
      // is what makes a lost-response success replay instead of colliding on
      // `resource_version`. But that guarantee only applies when we do not know
      // whether the server acted. A response with a status means it did act and
      // refused, so the key is spent — and this surface's own recovery advice
      // ("Try again after refreshing the comparison") CHANGES the body, which
      // under a retained key returns `409 idempotency_key_conflict` on every
      // subsequent attempt until the component unmounts.
      //
      // No status means no response (network failure): keep the key, because
      // the command may well have succeeded.
      if (getErrorStatus(error) !== undefined) keys.current.settle();
      void queryClient.invalidateQueries({ queryKey: ["run-approvals"] });
    },
  });
}
