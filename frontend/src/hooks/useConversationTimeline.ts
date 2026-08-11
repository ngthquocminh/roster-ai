import { useQuery } from "@tanstack/react-query";
import { getConversationTimeline } from "@/api/conversations";
export const conversationTimelineKey = (id: string) => ["conversation-timeline", id] as const;
/** `refetchInterval` is the labelled-polling fallback `useConversationStream`
 * switches on when the event stream cannot be re-established (AC2). It stays
 * `false` — no polling at all — whenever the stream is healthy. */
export function useConversationTimeline(id: string, refetchInterval: number | false = false) { return useQuery({ queryKey: conversationTimelineKey(id), queryFn: () => getConversationTimeline(id), enabled: Boolean(id), retry: false, refetchInterval }); }
