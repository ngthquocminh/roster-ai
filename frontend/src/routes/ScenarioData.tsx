import { useOutletContext, useParams } from "react-router";

import { ScenarioDataView } from "@/features/scenario-data/ScenarioDataView";

export function ScenarioData() {
  const { scenarioId = "" } = useParams();
  const { scenarioVersionId } = useOutletContext<{ scenarioVersionId: string }>();
  return <ScenarioDataView scenarioId={scenarioId} selectedVersion={scenarioVersionId} />;
}
