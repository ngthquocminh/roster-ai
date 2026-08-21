import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import { RunStatusBadge } from "@/components/runs/RunStatusBadge";
import { formatTimestamp } from "@/lib/formatTimestamp";
import type { ScheduleRunSummary } from "@/api/scheduleRuns";

/**
 * Renders a non-terminal run (`solver_queued`, `solver_running`,
 * `cancellation_requested`) as literal text plus its accepted timestamp.
 *
 * Trap 1: no solver publishes real-time progress, so this shows no spinner,
 * no percentage, and no invented ETA -- only the literal status and when the
 * run was accepted, matching the terminal rows' "static text only" contract.
 */
export function ProgressCard({ run }: Readonly<{ run: ScheduleRunSummary }>) {
  return (
    <div aria-live="polite" className="flex flex-col gap-1 text-sm" role="status">
      <div className="flex items-center gap-2">
        <RunStatusBadge status={run.status} />
        <IdentifierCopyButton identifierType="Run ID" value={run.schedule_run_id} />
      </div>
      <p className="text-muted-foreground">Accepted {formatTimestamp(run.created_at)}</p>
    </div>
  );
}
