import { useRef } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { decideApproval, type ApprovalDecision } from "@/api/approvals";
import { createIdempotencyKeyHolder } from "@/lib/idempotency";
import { getErrorStatus } from "@/lib/errors";
import { approvalKey } from "./useApproval";
export function useDecideApproval(id: string) {
  const keys = useRef(createIdempotencyKeyHolder()); const queryClient = useQueryClient();
  return useMutation({ mutationFn: (body: ApprovalDecision) => decideApproval(id, body, keys.current.current()), onSuccess: () => keys.current.settle(), onSettled: (_d, error) => { if (!error || getErrorStatus(error) !== undefined) keys.current.settle(); void queryClient.invalidateQueries({ queryKey: approvalKey(id) }); void queryClient.invalidateQueries({ queryKey: ["run-approvals"] }); void queryClient.invalidateQueries({ queryKey: ["conversation-timeline"] }); } });
}
