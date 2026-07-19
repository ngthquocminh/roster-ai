/**
 * The composed `/scenarios/:scenarioId/runs` Run History route
 * (RUN-01..RUN-05). Mounts at ScenarioLayout's `runs` child route,
 * replacing the prior `RunsPlaceholder`.
 *
 * Calls `useRuns` and `useTriggerRun` exactly once each and derives every
 * downstream prop from that single pair — no child component fetches or
 * mutates on its own:
 * - `runInProgress` / `activeRun` are derived via `hasActiveRun` /
 *   `newestActiveRun` (`@/lib/runStatus`) from the SAME `runsQuery.data`
 *   the table renders, so the panel, table, and button can never disagree
 *   about which run (if any) is in flight.
 * - `TriggerRunButton` gets `runsQuery.isLoading` / `trigger.isPending` /
 *   `trigger.error` directly — no local state duplicates mutation status.
 * - `RunInFlightPanel` gets `activeRun` (renders nothing when null).
 * - `RunHistoryTable` gets the raw `runsQuery` (mirrors `OverridesList`'s
 *   query-as-prop contract) plus `scenarioId` and the same `trigger.mutate`
 *   callback the header button uses, so its own empty-state CTA triggers
 *   the identical mutation.
 *
 * Deliberately NO scenario-existence 404 gate (unlike `Editor`): the runs
 * list endpoint does not 404 on an unknown scenarioId, it returns an empty
 * list — so a bogus deep-linked scenarioId falls through to
 * `RunHistoryTable`'s ordinary empty state (E4 backstop, T-3-09).
 * Deliberately NO cancel control and NO `solver_status` rendering anywhere
 * in this composition (RUN-03 honesty; scope guard).
 */
import { useParams } from "react-router";

import { RunHistoryTable } from "@/components/runs/RunHistoryTable";
import { RunInFlightPanel } from "@/components/runs/RunInFlightPanel";
import { TriggerRunButton } from "@/components/runs/TriggerRunButton";
import { useRuns } from "@/hooks/useRuns";
import { useTriggerRun } from "@/hooks/useTriggerRun";
import { hasActiveRun, newestActiveRun } from "@/lib/runStatus";

export function RunHistory() {
  const { scenarioId } = useParams();
  const runsQuery = useRuns(scenarioId as string);
  const trigger = useTriggerRun(scenarioId as string);

  const runs = runsQuery.data ?? [];
  const runInProgress = hasActiveRun(runs);
  const activeRun = newestActiveRun(runs);

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-8">
      <div className="flex items-center justify-between">
        <h2 className="text-[20px] leading-[1.2] font-semibold">
          Run History
        </h2>
        <TriggerRunButton
          onTrigger={() => trigger.mutate()}
          isLoadingList={runsQuery.isLoading || runsQuery.isFetching}
          runInProgress={runInProgress}
          isPending={trigger.isPending}
          error={trigger.error}
        />
      </div>
      <RunInFlightPanel run={activeRun} />
      <RunHistoryTable
        runsQuery={runsQuery}
        scenarioId={scenarioId as string}
        onTriggerRun={() => trigger.mutate()}
        triggerDisabled={trigger.isPending || runInProgress}
      />
    </div>
  );
}
