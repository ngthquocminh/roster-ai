import { useOutletContext, useParams } from "react-router";

import { ScenarioDataView } from "@/features/scenario-data/ScenarioDataView";

export function ScenarioData() {
  const { scenarioId = "" } = useParams();
  // `useOutletContext` returns null when no parent supplies one, so destructuring
  // it directly turns a routing mistake into a bare TypeError. The selected
  // version is only used to name the mismatch, so degrading to "unknown" is
  // strictly better than crashing the surface.
  const context = useOutletContext<{ scenarioVersionId?: string } | null>();
  return <ScenarioDataView scenarioId={scenarioId} selectedVersion={context?.scenarioVersionId} />;
}
