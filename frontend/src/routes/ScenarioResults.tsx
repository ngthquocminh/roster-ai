import { useEffect, useRef } from "react";
import { useParams } from "react-router";
import { CandidateScheduleTable } from "@/components/run-results/CandidateScheduleTable";
import { ComparisonSummary } from "@/components/run-results/ComparisonSummary";
import { RunOverview } from "@/components/run-results/RunOverview";
import { TerminalOutcomeCard } from "@/components/run-results/TerminalOutcomeCard";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { ProgressCard } from "@/components/runs/ProgressCard";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useScheduleRunResult } from "@/hooks/useScheduleRunResult";
import { useRequestApproval } from "@/hooks/useRequestApproval";
import { useRunApprovals } from "@/hooks/useRunApprovals";
import { ApprovalDecisionPanel } from "@/features/approvals/ApprovalDecisionPanel";
import { DebugDetailsPanel } from "@/features/provenance/DebugDetailsPanel";
import { USER_ERROR_COPY } from "@/lib/errors";

const NON_TERMINAL = new Set(["solver_queued", "solver_running", "cancellation_requested"]);
const NON_PROMOTABLE = new Set(["solver_infeasible", "solver_timed_out", "solver_cancelled", "solver_failed"]);
const KNOWN_RUN_STATUSES = new Set([...NON_TERMINAL, ...NON_PROMOTABLE, "solver_completed"]);

export function ScenarioResults() {
  const { runId = "", scenarioId = "" } = useParams();
  const query = useScheduleRunResult(runId);
  const requestApproval = useRequestApproval();
  const approvals = useRunApprovals(runId);
  const headingRef = useRef<HTMLHeadingElement>(null);
  // An unavailable baseline comparison is no longer an ERROR: the server returns
  // 200 with `comparison: null` and a literal reason, so the schedule, evidence,
  // and any pending approval stay readable. Only genuine transport/server
  // failures reach `query.isError`.
  const comparisonUnavailable = query.data?.comparison_unavailable_reason ?? null;

  useEffect(() => {
    headingRef.current?.focus();
  }, [runId]);

  return (
    <section aria-labelledby="scenario-results-heading" className="mx-auto mt-6 max-w-6xl space-y-5" data-run-id={runId} data-scenario-id={scenarioId}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h2 className="text-xl font-semibold outline-none" id="scenario-results-heading" ref={headingRef} tabIndex={-1}>Results</h2>
        <Button disabled={query.isFetching} onClick={() => { void query.refetch(); }} type="button" variant="outline">{query.isFetching ? "Refreshing…" : "Refresh"}</Button>
      </div>

      {query.isPending ? <div aria-label="Loading results" className="space-y-3"><Skeleton className="h-24 w-full" /><Skeleton className="h-48 w-full" /></div> : null}
      {query.isError ? <InlineAlert action={<Button onClick={() => { void query.refetch(); }} type="button" variant="outline">Retry</Button>} description={USER_ERROR_COPY.connection.description} title={USER_ERROR_COPY.connection.title} variant="destructive" /> : null}

      {comparisonUnavailable ? (
        <InlineAlert
          description={comparisonUnavailable}
          title="Baseline comparison unavailable"
          variant="destructive"
        />
      ) : null}

      {!query.isError && query.data && NON_TERMINAL.has(query.data.run.status) ? <ProgressCard run={query.data.run} /> : null}
      {!query.isError && query.data && NON_PROMOTABLE.has(query.data.run.status) ? <TerminalOutcomeCard run={query.data.run} /> : null}
      {!query.isError ? approvals.data?.items.map((approval) => <ApprovalDecisionPanel approvalId={approval.approval_id} key={approval.approval_id} />) : null}
      {!query.isError && query.data?.run.status === "solver_completed" && query.data.candidate && (query.data.comparison || comparisonUnavailable) ? (
        <>
          <RunOverview
            approvalsUnavailable={approvals.isError}
            baselineVersion={query.data.comparison?.expected_baseline_schedule_version ?? query.data.current_baseline_schedule_version ?? null}
            candidate={query.data.candidate}
            candidateVersionId={query.data.candidate.schedule_version_id}
            onRequestApproval={() => requestApproval.mutate({
              schedule_run_id: runId,
              expected_resource_version: query.data.run.resource_version,
              // The comparison can be exactly what is missing (refused), and the
              // approval request is parameterised on this value, so fall back to
              // the RESULT's baseline version.
              expected_baseline_schedule_version: query.data.comparison?.current_baseline_schedule_version ?? query.data.current_baseline_schedule_version ?? null,
            })}
            requestError={requestApproval.isError}
            requestPending={requestApproval.isPending}
            // FAIL CLOSED. `approvals.data` is `undefined` while the query is
            // loading and after it errors, so deriving this from `.some(...)`
            // alone left the control ENABLED whenever pending-state was
            // unknown. AD-14 already forbids the client cache being authority
            // for a decision; the server-side guard
            // (`approval_already_pending` + `uq_approval_request_pending_run`)
            // is the real one, and this must not invite the 409.
            pendingApproval={!approvals.isSuccess || approvals.data.items.some((item) => item.state === "pending")}
            stale={query.data.comparison?.stale ?? false}
          />
          <CandidateScheduleTable assignments={query.data.candidate.assignments} scenarioId={scenarioId} />
          {query.data.comparison ? <ComparisonSummary comparison={query.data.comparison} /> : null}
        </>
      ) : null}
      {!query.isError && query.data?.run.status === "solver_completed" && !comparisonUnavailable && (!query.data.candidate || !query.data.comparison) ? <InlineAlert description="The completed run did not return verifiable candidate evidence." title="Result unavailable" variant="destructive" /> : null}
      {!query.isError && query.data && !KNOWN_RUN_STATUSES.has(query.data.run.status) ? <InlineAlert description="This run reported a status this page does not recognize yet." title="Unrecognized run status" variant="destructive" /> : null}
      <DebugDetailsPanel evidenceRefs={query.data?.comparison?.evidence_refs ?? query.data?.candidate?.evidence_refs ?? null} runId={runId} scenarioId={scenarioId} />
    </section>
  );
}
