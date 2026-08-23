import { useParams, useSearchParams } from "react-router";

import { RunsTable } from "@/components/runs/RunsTable";
import { Button } from "@/components/ui/button";
import { PaginationControls } from "@/features/scenario-data/PaginationControls";
import { useScheduleRuns } from "@/hooks/useScheduleRuns";
import { getErrorStatus } from "@/lib/errors";
import { formatTimestamp } from "@/lib/formatTimestamp";

function readCursor(value: string | null): number {
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : 0;
}

export function ScenarioRuns() {
  const { scenarioId = "" } = useParams();
  // The cursor lives in the URL, not component state: a reload, a shared link,
  // or browser Back used to drop the planner silently back to page one. A
  // missing or malformed `cursor` reads as 0, and 0 is never written back to
  // the URL, so page one's address carries no stray param (Trap 6). On the
  // wire `listScheduleRuns` forwards whatever it is given, so page one does
  // send `cursor=0` -- which the route accepts (`ge=0`) and is the reason the
  // cursor is always a concrete number here rather than `undefined`.
  const [searchParams, setSearchParams] = useSearchParams();
  const cursor = readCursor(searchParams.get("cursor"));
  const setCursor = (next: number) => {
    setSearchParams(
      (current) => {
        const params = new URLSearchParams(current);
        if (next > 0) params.set("cursor", String(next));
        else params.delete("cursor");
        return params;
      },
      { replace: true },
    );
  };

  const query = useScheduleRuns(scenarioId, cursor);
  const runs = query.data?.items ?? [];
  const status = getErrorStatus(query.error);
  // A 401 is handled by `useScheduleRuns` itself (redirect). For anything else,
  // AC2's "without hiding saved data" splits the two cases the way
  // `ScenarioWorkspace` already does: only an error with NO cached page is
  // fatal and replaces the table. An error that arrives on top of a page the
  // planner can already see keeps the rows and labels them stale — a failed
  // background refetch must not blank a populated table.
  const failed = query.isError && status !== 401;
  const fatalError = failed && !query.data ? (query.error as Error) : null;
  const staleAfterFailedRefetch = failed && Boolean(query.data);

  return (
    <section aria-labelledby="scenario-runs-heading" className="mx-auto mt-6 max-w-6xl space-y-4" data-scenario-id={scenarioId}>
      <div className="flex items-center justify-between gap-2">
        <h2 className="text-xl font-semibold" id="scenario-runs-heading">Runs</h2>
        {/* Run state changes are planner-initiated today -- start and cancel
            both invalidate this list -- but no worker loop moves a run on its
            own yet (Story 3.11), and nothing polls. This is the explicit way
            to re-read the list without reloading the page. Deliberately a
            button and not a spinner or auto-refresh: AC3 forbids invented
            progress affordances. */}
        <Button
          className="min-h-11"
          disabled={query.isFetching}
          onClick={() => { void query.refetch(); }}
          type="button"
          variant="outline"
        >
          {query.isFetching ? "Refreshing…" : "Refresh"}
        </Button>
      </div>

      {staleAfterFailedRefetch ? (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 px-3 py-2">
          {/* Mirrors ScenarioWorkspace's approved stale label: only the message
              is a live region, the control stays outside it. */}
          <span className="text-sm" role="status">
            Stale — last verified at {formatTimestamp(new Date(query.dataUpdatedAt).toISOString())}
          </span>
          <Button className="min-h-11" onClick={() => { void query.refetch(); }} type="button" variant="outline">
            Retry
          </Button>
        </div>
      ) : null}

      <RunsTable
        emptyExplanation={
          cursor > 0
            ? "No runs on this page. The list may have changed since you paged forward."
            : "No runs yet for this scenario."
        }
        error={fatalError}
        isLoading={query.isPending}
        onRetry={() => { void query.refetch(); }}
        runs={runs}
        scenarioId={scenarioId}
      />

      {/* The shared pager, not a bespoke First/Next pair: the list route's
          envelope now carries `total_count`/`matching_count`, which is what
          `PaginationControls` needs to offer Previous/Last and a "showing
          X–Y of N" line. This route publishes no filters, so `hasFilters` is
          false and the two counts are equal. */}
      {!fatalError && query.data ? (
        <PaginationControls
          cursor={cursor}
          hasFilters={false}
          itemCount={runs.length}
          matchingCount={query.data.matching_count}
          nextCursor={query.data.next_cursor}
          onPageChange={setCursor}
          totalCount={query.data.total_count}
        />
      ) : null}
    </section>
  );
}
