import { useQuery } from "@tanstack/react-query";
import { getConversationTimeline } from "@/api/conversations";
export const conversationTimelineKey = (id: string) => ["conversation-timeline", id] as const;

/** Statuses during which an agent turn is running in the conversation (C7). */
const IN_FLIGHT_STATUSES: readonly string[] = ["agent_queued", "agent_running"];
export const isAgentTurnInFlight = (status: string | null | undefined) =>
  IN_FLIGHT_STATUSES.includes(status ?? "");

/**
 * How often the timeline is re-read while a turn is in flight. The stream merges
 * items but never `latest_agent_run_status`, and only the tab that sent the
 * message re-reads the timeline when its turn ends -- so a reload mid-turn (or a
 * second tab) would keep the Draft card's controls disabled indefinitely (code
 * review of story-5.11).
 */
export const IN_FLIGHT_POLL_INTERVAL_MS = 3_000;

/** `refetchInterval` is the labelled-polling fallback `useConversationStream`
 * switches on when the event stream cannot be re-established (AC2). Otherwise
 * the timeline polls only while an agent turn is in flight. */
export function useConversationTimeline(id: string, refetchInterval: number | false = false) {
  return useQuery({
    queryKey: conversationTimelineKey(id),
    queryFn: () => getConversationTimeline(id),
    enabled: Boolean(id),
    retry: false,
    refetchInterval: (query) => {
      if (refetchInterval !== false) return refetchInterval;
      return isAgentTurnInFlight(query.state.data?.latest_agent_run_status)
        ? IN_FLIGHT_POLL_INTERVAL_MS
        : false;
    },
  });
}
