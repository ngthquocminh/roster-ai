import { useMutation, useQueryClient } from "@tanstack/react-query";
import { sendMessage, type MessageCreate } from "@/api/conversations";
import { conversationTimelineKey } from "./useConversationTimeline";
import { conversationsKey } from "./useConversations";
export function useSendMessage(conversationId: string, scenarioId: string) {
  const queryClient = useQueryClient();
  return useMutation({ mutationFn: (body: MessageCreate) => sendMessage(conversationId, body), onSuccess: async () => { await Promise.all([queryClient.invalidateQueries({ queryKey: conversationTimelineKey(conversationId) }), queryClient.invalidateQueries({ queryKey: conversationsKey(scenarioId) })]); } });
}
