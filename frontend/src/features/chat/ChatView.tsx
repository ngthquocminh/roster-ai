import { useEffect, useState } from "react";
import { createConversation } from "@/api/conversations";
import { useConversations } from "@/hooks/useConversations";
import { useConversationTimeline } from "@/hooks/useConversationTimeline";
import { useSendMessage } from "@/hooks/useSendMessage";
import { ActivityTimeline } from "./ActivityTimeline";
import { Composer } from "./Composer";
import { ConversationList } from "./ConversationList";
export function ChatView({ scenarioId }: { scenarioId: string }) {
  const conversations = useConversations(scenarioId); const [selectedId, setSelectedId] = useState("");
  useEffect(() => { if (!selectedId && conversations.data?.[0]) setSelectedId(conversations.data[0].id); }, [conversations.data, selectedId]);
  const timeline = useConversationTimeline(selectedId); const mutation = useSendMessage(selectedId, scenarioId);
  const start = async () => { const value = await createConversation({ scenario_id: scenarioId }); setSelectedId(value.id); await conversations.refetch(); };
  return <section aria-labelledby="chat-title"><h1 id="chat-title">Chat</h1><button type="button" onClick={() => void start()}>New conversation</button><ConversationList conversations={conversations.data ?? []} selectedId={selectedId} onSelect={setSelectedId} />{selectedId ? <><ActivityTimeline items={timeline.data?.items ?? []} />{timeline.data?.latest_agent_run_status && <p>Agent run accepted — {timeline.data.latest_agent_run_status.replace("agent_", "")}</p>}<Composer isPending={mutation.isPending} onSend={(text) => mutation.mutateAsync({ text })} /></> : <p>Start a new conversation about this scenario—for example, ask about coverage, demand, or constraints.</p>}</section>;
}
