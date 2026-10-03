import { useParams } from "react-router";
import { ChatView } from "@/features/chat/ChatView";

export function ScenarioChat() {
  const { scenarioId = "" } = useParams();
  return <div className="mx-auto mt-6 max-w-3xl" data-scenario-id={scenarioId}><ChatView scenarioId={scenarioId} /></div>;
}
