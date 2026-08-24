import { useParams } from "react-router";
import { ComparisonSummary } from "@/components/run-results/ComparisonSummary";
import { TerminalOutcomeCard } from "@/components/run-results/TerminalOutcomeCard";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { ProgressCard } from "@/components/runs/ProgressCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useScheduleRunResult } from "@/hooks/useScheduleRunResult";
import { USER_ERROR_COPY } from "@/lib/errors";

const NON_TERMINAL = new Set(["solver_queued", "solver_running", "cancellation_requested"]);
const NON_PROMOTABLE = new Set(["solver_infeasible", "solver_timed_out", "solver_cancelled", "solver_failed"]);

export function ScenarioResults() {
  const { runId = "", scenarioId = "" } = useParams();
  const query = useScheduleRunResult(runId);

  return (
    <section aria-labelledby="scenario-results-heading" className="mx-auto mt-6 max-w-6xl space-y-5" data-run-id={runId} data-scenario-id={scenarioId}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold" id="scenario-results-heading">Results</h2>
        <Button disabled={query.isFetching} onClick={() => { void query.refetch(); }} type="button" variant="outline">{query.isFetching ? "Refreshing…" : "Refresh"}</Button>
      </div>

      {query.isPending ? <div aria-label="Loading results" className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-48 w-full" /></div> : null}
      {query.isError ? <InlineAlert action={<Button onClick={() => { void query.refetch(); }} type="button" variant="outline">Retry</Button>} description={USER_ERROR_COPY.connection.description} title={USER_ERROR_COPY.connection.title} variant="destructive" /> : null}

      {query.data && NON_TERMINAL.has(query.data.run.status) ? <ProgressCard run={query.data.run} /> : null}
      {query.data && NON_PROMOTABLE.has(query.data.run.status) ? <TerminalOutcomeCard run={query.data.run} /> : null}
      {query.data?.run.status === "solver_completed" && query.data.candidate && query.data.comparison ? (
        <>
          <ComparisonSummary comparison={query.data.comparison} />
          <section aria-labelledby="candidate-schedule-heading" className="rounded-xl border p-4">
            <h3 className="font-semibold" id="candidate-schedule-heading">Candidate schedule</h3>
            {query.data.candidate.assignments.length ? <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{query.data.candidate.assignments.map((assignment) => <li key={assignment.record_id}>{assignment.worker_id} · {assignment.task_id} · minutes {assignment.start_minute}–{assignment.end_minute}</li>)}</ul> : <p className="mt-2 text-sm">No assignments</p>}
          </section>
          <section aria-labelledby="result-evidence-heading" className="rounded-xl border p-4">
            <h3 className="font-semibold" id="result-evidence-heading">Evidence</h3>
            {query.data.comparison.evidence_refs.length ? <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">{query.data.comparison.evidence_refs.map((ref) => <li key={`${ref.group}:${ref.record_id}`}>{ref.group}: {ref.record_id}</li>)}</ul> : <p className="mt-2 text-sm">No evidence references</p>}
          </section>
        </>
      ) : null}
      {query.data?.run.status === "solver_completed" && (!query.data.candidate || !query.data.comparison) ? <InlineAlert description="The completed run did not return verifiable candidate evidence." title="Result unavailable" variant="destructive" /> : null}
    </section>
  );
}
