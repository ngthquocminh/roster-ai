import { useSearchParams } from "react-router";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BaselineAssignmentsPanel } from "./groups/BaselineAssignmentsPanel";
import { ConstraintsPanel } from "./groups/ConstraintsPanel";
import { DemandPanel } from "./groups/DemandPanel";
import { LocksPanel } from "./groups/LocksPanel";
import { OverviewPanel } from "./groups/OverviewPanel";
import { WorkAreasAndTasksPanel } from "./groups/WorkAreasAndTasksPanel";
import { WorkersPanel } from "./groups/WorkersPanel";

const groups = [
  ["overview", "Overview", OverviewPanel],
  ["work-areas-and-tasks", "Work areas and tasks", WorkAreasAndTasksPanel],
  ["workers", "Workers", WorkersPanel],
  ["demand", "Demand", DemandPanel],
  ["baseline-assignments", "Baseline assignments", BaselineAssignmentsPanel],
  ["locks", "Locks", LocksPanel],
  ["constraints-and-objectives", "Constraints and objectives", ConstraintsPanel],
] as const;
const knownGroups = new Set<string>(groups.map(([slug]) => slug));

export function ScenarioDataView({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get("group") ?? "overview";
  const selected = knownGroups.has(requested) ? requested : "overview";
  return (
    <section aria-labelledby="scenario-data-heading" className="mt-6">
      <h2 className="text-xl font-semibold" id="scenario-data-heading">Scenario Data</h2>
      <Tabs
        value={selected}
        onValueChange={(group) =>
          setSearchParams((previous) => ({ ...Object.fromEntries(previous), group }))
        }
      >
        <div className="mt-4 overflow-x-auto pb-2">
          <TabsList className="min-w-max" variant="line">
            {groups.map(([slug, label]) => <TabsTrigger className="min-h-11 px-3 data-active:text-primary data-active:after:bg-primary" key={slug} value={slug}>{label}</TabsTrigger>)}
          </TabsList>
        </div>
        {groups.map(([slug, _label, Panel]) => <TabsContent className="mt-4" key={slug} value={slug}><Panel scenarioId={scenarioId} /></TabsContent>)}
      </Tabs>
    </section>
  );
}
