import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { RunStatusBadge } from "@/components/runs/RunStatusBadge";

export function TerminalOutcomeCard({ run }: Readonly<{ run: ScheduleRunResult["run"] }>) {
  return (
    <section aria-labelledby="terminal-outcome-heading" className="space-y-4 rounded-xl border p-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-lg font-semibold" id="terminal-outcome-heading">Run outcome</h3>
        <RunStatusBadge status={run.status} />
      </div>
      <dl className="grid gap-3 text-sm sm:grid-cols-2">
        <div>
          <dt className="text-muted-foreground">Reason</dt>
          <dd className="font-medium">{run.reason ?? "No reason recorded"}</dd>
        </div>
        <div>
          <dt className="text-muted-foreground">Evidence</dt>
          <dd className="font-medium">No candidate evidence was produced</dd>
        </div>
      </dl>
    </section>
  );
}
