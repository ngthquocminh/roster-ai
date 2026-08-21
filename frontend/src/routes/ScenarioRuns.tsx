import { useState } from "react";
import { useParams } from "react-router";

import { RunsTable } from "@/components/runs/RunsTable";
import { Button } from "@/components/ui/button";
import { useScheduleRuns } from "@/hooks/useScheduleRuns";
import { getErrorStatus } from "@/lib/errors";

export function ScenarioRuns() {
  const { scenarioId = "" } = useParams();
  // Trap 6: `cursor` starts at 0 and is simply omitted from the query string
  // by `listScheduleRuns`/`compactQuery`-style callers when unset -- here it
  // is always a concrete number, so page one never sends a stray param.
  const [cursor, setCursor] = useState(0);
  const query = useScheduleRuns(scenarioId, cursor);
  const runs = query.data?.items ?? [];
  // AC2: a 401 is handled by `useScheduleRuns` itself (redirect); any other
  // failure still renders the workspace chrome around it, so Scenario Data
  // and the other tabs remain reachable (Trap 2) -- this route never early-
  // returns before the surrounding `ScenarioWorkspace` shell.
  const status = getErrorStatus(query.error);
  const error = query.isError && status !== 401 ? (query.error as Error) : null;

  return (
    <section aria-labelledby="scenario-runs-heading" className="mx-auto mt-6 max-w-6xl space-y-4" data-scenario-id={scenarioId}>
      <h2 className="text-xl font-semibold" id="scenario-runs-heading">Runs</h2>
      <RunsTable
        error={error}
        isLoading={query.isPending}
        onRetry={() => { void query.refetch(); }}
        runs={runs}
        scenarioId={scenarioId}
      />
      {!error && (cursor > 0 || query.data?.next_cursor != null) ? (
        <div aria-label="Run pages" className="flex justify-end gap-2" role="group">
          <Button className="min-h-11" disabled={cursor === 0} onClick={() => setCursor(0)} type="button" variant="outline">
            First
          </Button>
          <Button
            className="min-h-11"
            disabled={query.data?.next_cursor == null}
            onClick={() => setCursor(query.data?.next_cursor ?? cursor)}
            type="button"
            variant="outline"
          >
            Next
          </Button>
        </div>
      ) : null}
    </section>
  );
}
