import { useLocation, useSearchParams } from "react-router";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { EvidenceTargetPanel } from "@/features/evidence/EvidenceTargetPanel";
import { EVIDENCE_GROUP_TO_TAB, readTarget } from "@/features/evidence/locator";
import type { EvidenceOrigin } from "@/features/evidence/origin";
import type { ComponentType } from "react";
import { COLUMNS_BY_GROUP, type ScenarioDataListGroup } from "./columns";
import { ColumnChooser } from "./ColumnChooser";
import { FilterBar } from "./FilterBar";
import { FILTERS_BY_GROUP } from "./filters";
import { BaselineAssignmentsPanel } from "./groups/BaselineAssignmentsPanel";
import { ConstraintsPanel } from "./groups/ConstraintsPanel";
import { DemandPanel } from "./groups/DemandPanel";
import { LocksPanel } from "./groups/LocksPanel";
import { OverviewPanel } from "./groups/OverviewPanel";
import { WorkAreasAndTasksPanel } from "./groups/WorkAreasAndTasksPanel";
import { WorkersPanel } from "./groups/WorkersPanel";
import { useGroupControls, type GroupControls } from "./useGroupControls";
import { useColumnVisibility } from "./useColumnVisibility";

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

export function ScenarioDataView({ scenarioId, selectedVersion }: Readonly<{ scenarioId: string; selectedVersion?: string }>) {
  const [searchParams] = useSearchParams();
  const location = useLocation();
  const target = readTarget(searchParams);
  const origin = (location.state as { evidenceOrigin?: EvidenceOrigin } | null)?.evidenceOrigin;
  const requested = searchParams.get("group") ?? "overview";
  const selected = target ? EVIDENCE_GROUP_TO_TAB[target.group] : knownGroups.has(requested) ? requested : "overview";
  const isListGroup = selected !== "overview";
  const controlGroup = (isListGroup ? selected : "work-areas-and-tasks") as ScenarioDataListGroup;
  const controls = useGroupControls(controlGroup);
  const columns = COLUMNS_BY_GROUP[controlGroup];
  const visibility = useColumnVisibility(controlGroup, columns, searchParams.get("field") ?? undefined);
  return (
    <section aria-labelledby="scenario-data-heading" className="mt-6">
      <h2 className="text-xl font-semibold" id="scenario-data-heading">Scenario Data</h2>
      {target ? <EvidenceTargetPanel origin={origin} scenarioId={scenarioId} selectedVersion={selectedVersion} target={target} /> : null}
      <Tabs
        value={selected}
        onValueChange={controls.changeGroup}
      >
        <div className="mt-4 overflow-x-auto pb-2">
          <TabsList className="min-w-max" variant="line">
            {groups.map(([slug, label]) => <TabsTrigger className="min-h-11 px-3 data-active:text-primary data-active:after:bg-primary" key={slug} value={slug}>{label}</TabsTrigger>)}
          </TabsList>
        </div>
        {isListGroup ? (
          <div className="mt-4 space-y-3">
            <div className="flex flex-col gap-3 lg:flex-row-reverse lg:items-start lg:justify-between">
              <div className="space-y-2 lg:text-right">
                <div className="flex justify-start lg:justify-end"><ColumnChooser columns={columns} onVisibilityChange={visibility.setColumnVisible} revealedField={visibility.revealedColumn?.key} visibleKeys={visibility.visibleKeys} /></div>
                {visibility.revealedColumn ? <p className="text-sm text-muted-foreground">{visibility.revealedColumn.header} is shown because an evidence link targets it.</p> : null}
              </div>
              <div className="min-w-0 flex-1"><FilterBar activeFilters={controls.activeFilters} filters={FILTERS_BY_GROUP[controlGroup]} onApply={controls.applyFilters} onClear={controls.clearFilters} onRemove={controls.removeFilter} /></div>
            </div>
          </div>
        ) : null}
        {groups.map(([slug, _label, Panel]) => {
          const ListPanel = Panel as ComponentType<{ scenarioId: string; controls?: GroupControls; visibleColumns?: ReadonlySet<string> }>;
          return <TabsContent className="mt-4" key={slug} value={slug}>{slug === "overview" ? <OverviewPanel scenarioId={scenarioId} /> : <ListPanel controls={controls} scenarioId={scenarioId} visibleColumns={visibility.visibleKeys} />}</TabsContent>;
        })}
      </Tabs>
    </section>
  );
}
