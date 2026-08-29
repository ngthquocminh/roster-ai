import { useQuery } from "@tanstack/react-query";
import { listRunApprovals } from "@/api/approvals";

export const runApprovalsKey = (runId: string) => ["run-approvals", runId] as const;
export function useRunApprovals(runId: string) {
  return useQuery({ queryKey: runApprovalsKey(runId), queryFn: () => listRunApprovals(runId), enabled: Boolean(runId) });
}
