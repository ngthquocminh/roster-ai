import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";

import { getProposal } from "@/api/proposals";
import type { ScheduleRunSummary } from "@/api/scheduleRuns";
import { EmptyState } from "@/components/primitives/EmptyState";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { ProgressCard } from "@/components/runs/ProgressCard";
import { RunStatusBadge } from "@/components/runs/RunStatusBadge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { Table, TableBody, TableCaption, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useCancelScheduleRun } from "@/hooks/useCancelScheduleRun";
import { proposalKey } from "@/hooks/useProposal";
import { useStartScheduleRun } from "@/hooks/useStartScheduleRun";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { getErrorCode, getErrorStatus } from "@/lib/errors";

type RunStatus = ScheduleRunSummary["status"];

//: The AD-7 statuses that permit each control. Cancel is deliberately absent
//: from `cancellation_requested` -- Trap 5's own guard test names only
//: `solver_running`/`solver_queued`, and re-showing Cancel on a run whose
//: cancellation is already in flight has no new action for a planner to take
//: (the command is idempotent if replayed, but nothing here needs to replay
//: it). This resolves a wording tension between the Architecture guardrails'
//: per-status Actions table (the more specific source) and its more general
//: "Cancel button guard" paragraph.
const NON_TERMINAL: ReadonlySet<RunStatus> = new Set([
  "solver_queued",
  "solver_running",
  "cancellation_requested",
]);
const CANCELLABLE: ReadonlySet<RunStatus> = new Set(["solver_queued", "solver_running"]);
const RETRYABLE: ReadonlySet<RunStatus> = new Set([
  "solver_completed",
  "solver_infeasible",
  "solver_timed_out",
  "solver_cancelled",
  "solver_failed",
]);
//: `solver_cancelled` gets Retry only (Architecture guardrails' Actions
//: table) -- no candidate exists to view.
const VIEWABLE: ReadonlySet<RunStatus> = new Set([
  "solver_completed",
  "solver_infeasible",
  "solver_timed_out",
  "solver_failed",
  "solver_queued",
  "solver_running",
  "cancellation_requested",
]);

const RUN_CODE_MESSAGES: Readonly<Record<string, string>> = {
  stale_resource_version: "This changed since the page loaded. Refresh to see the current version.",
  idempotency_key_conflict: "An earlier command is still on record for this run. Reload the page and try again.",
  run_not_cancellable: "This run is no longer cancellable — it may have already finished.",
  proposal_not_found: "The proposal behind this run is no longer available.",
  rejected_proposal: "That proposal was rejected, so it cannot be run again.",
  scenario_unavailable: "The scenario could not be read just now. Try again shortly.",
  site_concurrency_exhausted: "This site is at its run limit. Try again shortly.",
  compute_not_granted: "Optimization is turned off for this site, so no run can be started.",
};

function commandMessage(error: unknown): string {
  const code = getErrorCode(error);
  if (code && Object.hasOwn(RUN_CODE_MESSAGES, code)) return RUN_CODE_MESSAGES[code];
  const status = getErrorStatus(error);
  if (status === 429) return "This site is at its run limit. Try again shortly.";
  return "That command did not complete. Try again.";
}

function CancelButton({ run }: Readonly<{ run: ScheduleRunSummary }>) {
  const cancellation = useCancelScheduleRun(run.schedule_run_id);
  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        className="min-h-11"
        disabled={cancellation.isPending}
        onClick={() => cancellation.mutate({ expected_resource_version: run.resource_version })}
        type="button"
        variant="destructive"
      >
        Cancel
      </Button>
      {cancellation.isSuccess ? (
        <p className="text-xs text-muted-foreground" role="status">
          Cancellation requested.
        </p>
      ) : null}
      {cancellation.isError ? (
        <InlineAlert description={commandMessage(cancellation.error)} title="Cancel not applied" variant="destructive" />
      ) : null}
    </div>
  );
}

function RetryButton({ run }: Readonly<{ run: ScheduleRunSummary }>) {
  // Trap 3: Retry re-activates the existing Run optimization flow -- the same
  // `useStartScheduleRun` mutation `DraftCard`'s "Run optimization" button
  // calls -- rather than a new route. It reads the proposal's CURRENT
  // resource version (not this run's frozen historical one): the proposal may
  // have been revised since this run was accepted, and retrying against a
  // stale version would only earn an immediate `stale_resource_version`.
  //
  // That read happens ON CLICK, not on mount. As a `useProposal` hook it fired
  // once per retryable row -- up to a full page of parallel proposal reads on
  // first paint -- and gating `disabled` on its result was the speculative
  // disable the guardrails argue against: one transient failure left Retry
  // permanently inert with no way to force the attempt. `fetchQuery` still
  // populates the same `["proposal", id]` cache entry the hook would have.
  const queryClient = useQueryClient();
  const start = useStartScheduleRun();
  const [readFailed, setReadFailed] = useState(false);
  const [reading, setReading] = useState(false);
  return (
    <div className="flex flex-col items-start gap-1">
      <Button
        className="min-h-11"
        disabled={reading || start.isPending}
        onClick={() => {
          setReadFailed(false);
          setReading(true);
          void queryClient
            .fetchQuery({
              queryKey: proposalKey(run.proposal_id),
              queryFn: () => getProposal(run.proposal_id),
            })
            .then((proposal) => {
              start.mutate({
                proposal_id: run.proposal_id,
                expected_resource_version: proposal.resource_version,
              });
            })
            .catch(() => setReadFailed(true))
            .finally(() => setReading(false));
        }}
        type="button"
        variant="secondary"
      >
        Retry
      </Button>
      {start.isSuccess ? (
        <p className="text-xs text-muted-foreground" role="status">
          Run <span className="font-mono">{start.data.schedule_run_id}</span> queued.
        </p>
      ) : null}
      {start.isError ? (
        <InlineAlert description={commandMessage(start.error)} title="Retry not applied" variant="destructive" />
      ) : null}
      {readFailed ? (
        <InlineAlert description="The proposal behind this run could not be read. Try again." title="Retry not applied" variant="destructive" />
      ) : null}
    </div>
  );
}

//: Epic 4 owns the real approval command (AD-10/Story 4.1); no route exists
//: yet. Rendering it disabled keeps the control visibly named (AC1) without
//: fabricating a working command Story 3.7 does not own.
function ApproveButton() {
  return (
    <Button className="min-h-11" disabled title="Approval is not available yet" type="button" variant="outline">
      Approve as baseline
    </Button>
  );
}

function RunActions({ run, scenarioId }: Readonly<{ run: ScheduleRunSummary; scenarioId: string }>) {
  return (
    <div className="flex flex-wrap items-start gap-2">
      {CANCELLABLE.has(run.status) ? <CancelButton run={run} /> : null}
      {VIEWABLE.has(run.status) ? (
        <Button asChild className="min-h-11" size="sm" variant="outline">
          <Link to={`/scenarios/${scenarioId}/runs/${run.schedule_run_id}`}>
            {NON_TERMINAL.has(run.status) ? "View progress" : "View results"}
          </Link>
        </Button>
      ) : null}
      {RETRYABLE.has(run.status) ? <RetryButton run={run} /> : null}
      {run.status === "solver_completed" ? <ApproveButton /> : null}
    </div>
  );
}

function StatusCell({ run }: Readonly<{ run: ScheduleRunSummary }>) {
  // AC3: non-terminal runs render as static "In progress"-style text with a
  // timestamp (ProgressCard), never a percentage/ETA/spinner. Terminal runs
  // render their literal status alone.
  if (NON_TERMINAL.has(run.status)) return <ProgressCard run={run} />;
  return <RunStatusBadge status={run.status} />;
}

export function RunsTable({
  emptyExplanation = "No runs yet for this scenario.",
  error,
  isLoading,
  onRetry,
  runs,
  scenarioId,
}: Readonly<{
  runs: ScheduleRunSummary[];
  isLoading: boolean;
  error: Error | null;
  scenarioId: string;
  onRetry?: () => void;
  /** Page-aware copy: "no runs yet" is the wrong sentence on page three. */
  emptyExplanation?: string;
}>) {
  if (isLoading) {
    return (
      <div aria-label="Loading runs" className="space-y-2" role="status">
        {[0, 1, 2].map((row) => (
          <Skeleton className="h-10 w-full" key={row} />
        ))}
      </div>
    );
  }
  if (error) {
    return (
      <InlineAlert
        action={
          onRetry ? (
            <Button className="min-h-11" onClick={onRetry} type="button" variant="outline">
              Retry
            </Button>
          ) : undefined
        }
        description="Try again. If the problem continues, reload the page."
        title="Couldn't load this content."
        variant="destructive"
      />
    );
  }
  if (runs.length === 0) {
    return <EmptyState explanation={emptyExplanation} />;
  }
  return (
    <div aria-label="Runs" className="overflow-x-auto rounded-md border" role="region" tabIndex={0}>
      <Table className="min-w-max">
        <TableCaption className="sr-only">Runs for this scenario, newest first</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead scope="col">Run ID</TableHead>
            <TableHead scope="col">Status</TableHead>
            <TableHead scope="col">Accepted</TableHead>
            <TableHead scope="col">Updated</TableHead>
            <TableHead scope="col">Scenario version</TableHead>
            <TableHead scope="col">Proposal version</TableHead>
            <TableHead scope="col">Baseline version</TableHead>
            <TableHead scope="col">Actions</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow key={run.schedule_run_id}>
              <TableCell><IdentifierCopyButton identifierType="Run ID" value={run.schedule_run_id} /></TableCell>
              <TableCell><StatusCell run={run} /></TableCell>
              <TableCell>{formatTimestamp(run.created_at)}</TableCell>
              {/* AC1's "updated time": the newest event on the run's stream,
                  falling back server-side to created_at. Deliberately NOT
                  finished_at, which is null for every non-terminal run --
                  exactly the rows a planner opens this table to monitor. */}
              <TableCell>{formatTimestamp(run.updated_at)}</TableCell>
              <TableCell><IdentifierCopyButton identifierType="Scenario version" value={run.scenario_version_id} /></TableCell>
              <TableCell>{run.proposal_version}</TableCell>
              {/* Trap 4: Story 3.1 Decision 7 -- baseline stays None today.
                  Renders as "—", never "" or 0 (those would suggest a value
                  that could appear later without a code change). */}
              <TableCell>{run.baseline_schedule_version ?? "—"}</TableCell>
              <TableCell><RunActions run={run} scenarioId={scenarioId} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
