import { useQuery } from "@tanstack/react-query";
import { getConversationTimeline } from "@/api/conversations";
export const conversationTimelineKey = (id: string) => ["conversation-timeline", id] as const;
export function useConversationTimeline(id: string) { return useQuery({ queryKey: conversationTimelineKey(id), queryFn: () => getConversationTimeline(id), enabled: Boolean(id), retry: false }); }
