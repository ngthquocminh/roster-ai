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
 *
 * It carries NO copy-identifier control. It renders inside `RunsTable`'s
 * Status cell, whose row already has a `Copy Run ID` button in the Run ID
 * column -- a second one gave every in-flight row two buttons with the
 * byte-identical accessible name `Copy Run ID <uuid>`, which is exactly what
 * AC1's "separately labelled" forbids.
 *
 * `role="status"` already implies `aria-live="polite"`, so the attribute is
 * not repeated; and with no copy button left there is no focusable control
 * inside the live region.
 */
export function ProgressCard({ run }: Readonly<{ run: ScheduleRunSummary }>) {
  return (
    <div className="flex flex-col gap-1 text-sm" role="status">
      <RunStatusBadge status={run.status} />
      <p className="text-muted-foreground">Accepted {formatTimestamp(run.created_at)}</p>
    </div>
  );
}
