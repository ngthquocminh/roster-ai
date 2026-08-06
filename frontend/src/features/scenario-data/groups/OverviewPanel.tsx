import { TableBody, TableCell, TableHead, TableRow } from "@/components/ui/table";
import { useScenarioOverview } from "@/hooks/useScenarioProjection";
import { getErrorStatus } from "@/lib/errors";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { ScenarioDataGroupState } from "../ScenarioDataGroupState";
import { ScenarioDataTable } from "../ScenarioDataTable";

// A label/value pair per row, not a header row — the column count is fixed
// by that shape rather than derived from a headers array.
const COLUMN_COUNT = 2;

export function OverviewPanel({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const query = useScenarioOverview(scenarioId);
  const data = query.data;
  const rows = data
    ? ([
        ["Scenario name", data.scenario_name],
        ["Scenario ID", data.scenario_id, true],
        ["Fixture version", data.fixture_version, true],
        ["Baseline version", data.baseline_schedule_version ?? "Not established", true],
        ["Time horizon", `starts ${formatTimestamp(data.horizon_start)}, ${data.horizon_minutes} minutes`],
        ["Site timezone", data.site_timezone],
        ["Last verified", formatTimestamp(data.projection_generated_at)],
        ["Work areas", data.work_area_count],
        ["Tasks", data.task_count],
        ["Workers", data.worker_count],
        ["Demand intervals", data.demand_interval_count],
        ["Baseline assignments", data.baseline_assignment_count],
        ["Locks", data.lock_count],
        ["Constraints and objectives", data.constraint_count],
      ] as const)
    : [];

  return (
    <ScenarioDataGroupState
      columnCount={COLUMN_COUNT}
      errorStatus={getErrorStatus(query.error)}
      isEmpty={!data}
      isError={query.isError}
      isPending={query.isPending}
      onRetry={() => {
        void query.refetch();
      }}
    >
      <ScenarioDataTable caption="Overview">
        <TableBody>
          {rows.map(([label, value, mono]) => (
            <TableRow key={label}>
              <TableHead className="bg-muted/40" scope="row">
                {label}
              </TableHead>
              <TableCell className={mono ? "font-mono text-xs" : undefined} title={mono ? String(value) : undefined}>
                {value}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </ScenarioDataTable>
    </ScenarioDataGroupState>
  );
}
