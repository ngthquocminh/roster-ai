import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { archiveConversation, listConversations } from "@/api/conversations";
export const conversationsKey = (scenarioId: string) => ["conversations", scenarioId] as const;
export function useConversations(scenarioId: string) { return useQuery({ queryKey: conversationsKey(scenarioId), queryFn: () => listConversations(scenarioId), enabled: Boolean(scenarioId), retry: false }); }
export function useArchiveConversation(scenarioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (conversationId: string) => archiveConversation(conversationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: conversationsKey(scenarioId) }),
  });
}
