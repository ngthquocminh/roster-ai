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
      // The planner's message has been persisted, so this mutation resolves
      // here and the composer clears its draft. Executing an agent turn is a
      // separate, potentially long-running operation; coupling it to send
      // success kept already-sent text in the input until the run finished.
      void (async () => {
        try {
          await executeTurn(conversationId, accepted.agent_run_id);
        } finally {
          // Whether execution completes or rejects, replace queued optimistic
          // state with the server's persisted timeline.
          await Promise.all([
            queryClient.invalidateQueries({ queryKey: conversationTimelineKey(conversationId) }),
            queryClient.invalidateQueries({ queryKey: conversationsKey(scenarioId) }),
          ]);
        }
      })().catch(() => undefined);
      return accepted;
    },
  });
}
