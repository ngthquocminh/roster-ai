import { useParams } from "react-router";

import { ScenarioDataView } from "@/features/scenario-data/ScenarioDataView";

export function ScenarioData() {
  const { scenarioId = "" } = useParams();
  return <ScenarioDataView scenarioId={scenarioId} />;
}
