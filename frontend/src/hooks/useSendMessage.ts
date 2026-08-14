import { useMutation, useQueryClient } from "@tanstack/react-query";
import { executeTurn, sendMessage, type MessageCreate, type Timeline } from "@/api/conversations";
import { conversationTimelineKey } from "./useConversationTimeline";
import { conversationsKey } from "./useConversations";
export function useSendMessage(conversationId: string, scenarioId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (body: MessageCreate) => {
      const accepted = await sendMessage(conversationId, body);
      // Preserve the accepted queued state between the two request-path calls.
      // The terminal response replaces it only after execute completes.
      queryClient.setQueryData<Timeline>(conversationTimelineKey(conversationId), (current) =>
        current
          ? {
              ...current,
              resource_version: accepted.resource_version,
              latest_agent_run_status: accepted.agent_run_status,
              items: [...current.items, accepted.activity],
            }
          : current,
      );
      return executeTurn(conversationId, accepted.agent_run_id);
    },
    // onSettled, not onSuccess: the optimistic write above has already put the
    // accepted message and `agent_queued` into the cache, so an executeTurn
    // rejection (409, a 500, a dropped connection) would otherwise leave the
    // timeline showing a queued turn that never refetches and never resolves.
    // Refetching on both paths lets the server state win either way.
    onSettled: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: conversationTimelineKey(conversationId) }),
        queryClient.invalidateQueries({ queryKey: conversationsKey(scenarioId) }),
      ]);
    },
  });
}
