import { useQuery } from "@tanstack/react-query";
import { getApproval } from "@/api/approvals";
export const approvalKey = (id: string) => ["approval", id] as const;
export function useApproval(id: string) { return useQuery({ queryKey: approvalKey(id), queryFn: () => getApproval(id), enabled: Boolean(id) }); }
