import { useParams } from "react-router";
import { WorkspaceTabPlaceholder } from "@/components/layout/WorkspaceTabPlaceholder";

export function ScenarioResults() {
  const { runId = "", scenarioId = "" } = useParams();
  return <div className="mx-auto max-w-6xl" data-run-id={runId} data-scenario-id={scenarioId}><WorkspaceTabPlaceholder description="Run results are not available yet." title="Results" /></div>;
}
