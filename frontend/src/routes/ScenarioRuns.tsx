import { useParams } from "react-router";
import { WorkspaceTabPlaceholder } from "@/components/layout/WorkspaceTabPlaceholder";

export function ScenarioRuns() {
  const { scenarioId = "" } = useParams();
  return <div className="mx-auto max-w-6xl" data-scenario-id={scenarioId}><WorkspaceTabPlaceholder description="Run history and manual optimization are not available yet." title="Runs" /></div>;
}
