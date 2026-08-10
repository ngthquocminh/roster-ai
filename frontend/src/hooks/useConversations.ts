import { useQuery } from "@tanstack/react-query";
import { listConversations } from "@/api/conversations";
export const conversationsKey = (scenarioId: string) => ["conversations", scenarioId] as const;
export function useConversations(scenarioId: string) { return useQuery({ queryKey: conversationsKey(scenarioId), queryFn: () => listConversations(scenarioId), enabled: Boolean(scenarioId), retry: false }); }
