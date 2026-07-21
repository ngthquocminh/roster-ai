/**
 * RES-01..RES-06's composed Results view (D-12) — mounts at
 * `/scenarios/:scenarioId/runs/:runId`, replacing `ResultsPlaceholder`. This
 * is the integration seam: it branches on `RunOut.status` FIRST, before any
 * results content renders, then feeds one `RunResult` response to six
 * presentational child components.
 *
 * Calls `useRun` once and `useRunResult(runId, { enabled: status ===
 * "COMPLETED" })` once — mirrors `RunHistory.tsx`'s "one query pair drives
 * everything, no child fetches independently" precedent. `useRunResult`'s
 * `enabled` gate is what keeps `GET /runs/{run_id}/result` from ever firing
 * (and 409ing) before the run reaches `COMPLETED` — the route stays
 * deep-linkable for any run status (D-12).
 *
 * Branch precedence (Application Structure / UI-SPEC E1):
 *   1. `runQuery.isLoading` — centered spinner (RunHistoryTable's loading
 *      convention), before any status is known.
 *   2. `runQuery.isError` — `ErrorBanner` (SHELL-04); a failed `GET
 *      /runs/{id}` itself is a different failure than a `FAILED` run.
 *   3. `PENDING`/`RUNNING` — `RunInFlightPanel` reused verbatim (Phase 3, no
 *      new copy); nothing else renders below it.
 *   4. `FAILED` — a page-level destructive `Alert` with shared fixed copy;
 *      persisted `run.error` diagnostics never become render input, and
 *      nothing else renders below it.
 *   5. `COMPLETED` — gated on `resultQuery`: while the result is still
 *      loading/erroring, an honest interim state (spinner / `ErrorBanner`);
 *      once `resultQuery.isSuccess`, the full results body renders in the
 *      UI-SPEC Application Structure order (heading+metadata,
 *      WarningsBanner, CoverageSummary, CoverageByDayTable,
 *      DemandVsServedChart, ScheduleTable, InsightPanel).
 *
 * `InsightPanel` mounts unconditionally alongside the other COMPLETED-branch
 * sections — its own `useRunInsights` mutation is structurally isolated
 * (RES-05), so a `502` there re-renders only that section while the
 * coverage/chart/schedule sections above it stay mounted and interactive.
 */
import { useParams } from "react-router";
import { LoaderCircle } from "lucide-react";

import { ErrorBanner } from "@/components/layout/ErrorBanner";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { CoverageByDayTable } from "@/components/results/CoverageByDayTable";
import { CoverageSummary } from "@/components/results/CoverageSummary";
import { DemandVsServedChart } from "@/components/results/DemandVsServedChart";
import { InsightPanel } from "@/components/results/InsightPanel";
import { ScheduleTable } from "@/components/results/ScheduleTable";
import { WarningsBanner } from "@/components/results/WarningsBanner";
import { RunInFlightPanel } from "@/components/runs/RunInFlightPanel";
import { useRun } from "@/hooks/useRun";
import { useRunResult } from "@/hooks/useRunResult";
import { USER_ERROR_COPY } from "@/lib/errors";
import { formatTimestamp } from "@/lib/formatTimestamp";

function CenteredSpinner({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center gap-3 py-16">
      <LoaderCircle
        className="size-6 animate-spin text-muted-foreground"
        aria-hidden="true"
      />
      <p className="text-sm leading-[1.5] text-muted-foreground">{label}</p>
    </div>
  );
}

export function ResultsView() {
  const { runId } = useParams();
  const runQuery = useRun(runId as string);
  const resultQuery = useRunResult(runId as string, {
    enabled: runQuery.data?.status === "COMPLETED",
  });

  if (runQuery.isLoading) {
    return <CenteredSpinner label="Loading run…" />;
  }

  if (runQuery.isError) {
    return <ErrorBanner error={runQuery.error} />;
  }

  const run = runQuery.data;

  if (run?.status === "PENDING" || run?.status === "RUNNING") {
    return <RunInFlightPanel run={run} />;
  }

  if (run?.status === "FAILED") {
    return (
      <Alert variant="destructive" className="mx-6 my-4 max-w-3xl">
        <AlertTitle>{USER_ERROR_COPY.runFailure.title}</AlertTitle>
        <AlertDescription className="whitespace-normal break-words">
          {USER_ERROR_COPY.runFailure.description}
        </AlertDescription>
      </Alert>
    );
  }

  // COMPLETED (or an unrecognized status — falls through to the same honest
  // interim/never-blank-screen handling rather than a silent no-op).
  if (resultQuery.isLoading) {
    return <CenteredSpinner label="Loading results…" />;
  }

  if (resultQuery.isError) {
    return <ErrorBanner error={resultQuery.error} />;
  }

  if (!resultQuery.isSuccess) {
    return null;
  }

  const result = resultQuery.data;

  return (
    <div className="mx-auto flex max-w-5xl flex-col gap-4 px-6 py-8">
      <div>
        <h1 className="text-[20px] leading-[1.2] font-semibold">
          Run Results
        </h1>
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Completed {run?.finished_at ? formatTimestamp(run.finished_at) : "—"}
        </p>
      </div>
      <WarningsBanner warnings={result.warnings ?? []} />
      <CoverageSummary
        total_cost={result.metrics.total_cost}
        total_unmet_hours={result.metrics.total_unmet_hours}
      />
      <CoverageByDayTable coverage_by_day={result.metrics.coverage_by_day} />
      <DemandVsServedChart
        coverage_by_function={result.metrics.coverage_by_function}
      />
      <ScheduleTable schedule={result.schedule} />
      {/* key={runId}: forces a remount on navigation between runs (React
          Router re-renders the same ResultsView instance across a
          param-only route change) — otherwise useRunInsights' mutation
          state isn't keyed by runId and a previous run's report stays
          displayed, mislabeled as the new run's (CR-01). */}
      <InsightPanel key={runId} runId={runId as string} />
    </div>
  );
}
