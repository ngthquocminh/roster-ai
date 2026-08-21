import { StatusBadge } from "@/components/primitives/StatusBadge";
import { cn } from "@/lib/utils";
import type { ScheduleRunSummary } from "@/api/scheduleRuns";

type RunStatus = ScheduleRunSummary["status"];

/**
 * AD-7's closed status graph, rendered as distinct literal text.
 *
 * Story 3.7 AC3: no percentage, ETA, feasibility forecast, or invented state
 * (e.g. "Optimizing…", "Almost done"). Each of the eight statuses gets its
 * own copy so a planner reads the exact outcome, not a paraphrase, and no two
 * statuses render the same text. Colour is an accent only -- the text alone
 * always carries the meaning (matches Story 3.6's "literal non-colour status
 * meaning" accessibility contract). Composes Story 1.6's `StatusBadge`
 * primitive rather than a new badge shell.
 */
const STATUS_COPY: Record<RunStatus, string> = {
  solver_queued: "Queued",
  solver_running: "In progress",
  cancellation_requested: "Cancellation requested",
  solver_completed: "Completed",
  solver_infeasible: "Infeasible",
  solver_timed_out: "Timed out",
  solver_cancelled: "Cancelled",
  solver_failed: "Failed",
};

const STATUS_ACCENT: Record<RunStatus, string> = {
  solver_queued: "bg-transparent border-muted-foreground/40 text-muted-foreground",
  solver_running: "bg-transparent border-primary/40 text-primary",
  cancellation_requested: "bg-transparent border-amber-500/50 text-amber-700 dark:text-amber-400",
  solver_completed: "bg-transparent border-emerald-500/50 text-emerald-700 dark:text-emerald-400",
  solver_infeasible: "bg-transparent border-destructive/40 text-destructive",
  solver_timed_out: "bg-transparent border-amber-500/50 text-amber-700 dark:text-amber-400",
  solver_cancelled: "bg-transparent border-muted-foreground/40 text-muted-foreground",
  solver_failed: "bg-transparent border-destructive/40 text-destructive",
};

export function RunStatusBadge({ status }: Readonly<{ status: RunStatus }>) {
  return (
    <StatusBadge className={cn(STATUS_ACCENT[status])} status={STATUS_COPY[status]} />
  );
}
