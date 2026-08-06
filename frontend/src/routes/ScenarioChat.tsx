import { useParams } from "react-router";
import { WorkspaceTabPlaceholder } from "@/components/layout/WorkspaceTabPlaceholder";

export function ScenarioChat() {
  const { scenarioId = "" } = useParams();
  return <div className="mx-auto max-w-6xl" data-scenario-id={scenarioId}><WorkspaceTabPlaceholder description="Conversational investigation is not available yet." title="Chat" /></div>;
}
