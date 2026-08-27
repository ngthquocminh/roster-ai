import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { requestApproval, type ApprovalRequest } from "@/api/approvals";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";

export function useRequestApproval() {
  const keys = useRef(createIdempotencyKeyHolder());
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ApprovalRequest) => requestApproval(body, keys.current.current()),
    onSuccess: () => { keys.current.settle(); void queryClient.invalidateQueries({ queryKey: ["run-approvals"] }); },
  });
}
