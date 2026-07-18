/**
 * RUN-04/RUN-05 run history table — every run for a scenario, newest-first
 * (server ordering, no client re-sort), replicating ScenarioTable's/
 * OverridesList's loading/error/empty/populated/overflow state machine (see
 * those files' header comments for the identical rationale).
 *
 * Takes the raw `runsQuery` (`UseQueryResult<RunOut[]>`) as a prop — never
 * calls a `useRuns()` hook itself — mirroring `OverridesList`'s
 * `overridesQuery` prop, so RunHistory's single query instance (03-05) can
 * drive both the in-flight panel and this table without a duplicate fetch.
 *
 * The empty state's "Run Scenario" button is a plain `Button` + callback
 * (`onTriggerRun`), exactly like `ScenarioTable`'s `onCreateScenario` —
 * deliberately NOT the stateful `TriggerRunButton` from 03-04, to avoid a
 * cross-plan coupling.
 *
 * `solver_status` is never read or rendered anywhere in this file (UI-SPEC:
 * "solver_status is deliberately never rendered in this view") — a
 * COMPLETED run always reads as unambiguous, neutral success here,
 * regardless of what the solver actually achieved.
 *
 * `run.error` and every other cell value render only as JSX text children
 * (T-3-05/T-1-03 convention) — React's default text-node escaping is the
 * complete mitigation; no dangerouslySetInnerHTML anywhere in this file.
 */
import { useNavigate } from "react-router";
import { LoaderCircle } from "lucide-react";
import type { UseQueryResult } from "@tanstack/react-query";

import { ErrorBanner } from "@/components/layout/ErrorBanner";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { RunStatusLabel } from "./RunStatusLabel";
import { formatTimestamp } from "@/lib/formatTimestamp";
import type { components } from "@/api/schema";

type RunOut = components["schemas"]["RunOut"];

const FAILED_NO_ERROR_COPY = "Failed — no error details were recorded.";

function TimestampCell({ value }: { value?: string | null }) {
  if (!value) {
    return <span className="text-muted-foreground">—</span>;
  }
  return <>{formatTimestamp(value)}</>;
}

export function RunHistoryTable({
  runsQuery,
  scenarioId,
  onTriggerRun,
}: {
  runsQuery: UseQueryResult<RunOut[], unknown>;
  scenarioId: string;
  onTriggerRun?: () => void;
}) {
  const navigate = useNavigate();
  const { data, isLoading, isError, error } = runsQuery;

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center gap-3 py-16">
        <LoaderCircle
          className="size-6 animate-spin text-muted-foreground"
          aria-hidden="true"
        />
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Loading runs…
        </p>
      </div>
    );
  }

  if (isError) {
    return <ErrorBanner error={error} />;
  }

  const runs = data ?? [];

  if (runs.length === 0) {
    return (
      <div className="flex flex-col items-center gap-4 py-16 text-center">
        <h2 className="text-[20px] leading-[1.2] font-semibold">
          No runs yet
        </h2>
        <p className="text-sm leading-[1.5] text-muted-foreground">
          Trigger a run to solve this scenario.
        </p>
        <Button type="button" onClick={onTriggerRun}>
          Run Scenario
        </Button>
      </div>
    );
  }

  const goToRun = (runId: string) =>
    navigate(`/scenarios/${scenarioId}/runs/${runId}`);

  return (
    <div className="max-h-[420px] overflow-y-auto rounded-md border border-border">
      <Table className="table-fixed">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[34%]">Status</TableHead>
            <TableHead className="w-[22%]">Created</TableHead>
            <TableHead className="w-[22%]">Started</TableHead>
            <TableHead className="w-[22%]">Finished</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {runs.map((run) => (
            <TableRow
              key={run.id}
              tabIndex={0}
              className="cursor-pointer"
              onClick={() => goToRun(run.id)}
              onKeyDown={(event) => {
                if (event.key === "Enter" || event.key === " ") {
                  event.preventDefault();
                  goToRun(run.id);
                }
              }}
            >
              <TableCell className="align-top whitespace-normal">
                <RunStatusLabel status={run.status} />
                {run.status === "FAILED" && (
                  <p className="mt-1 text-sm leading-[1.5] break-words whitespace-pre-wrap text-destructive">
                    {run.error || FAILED_NO_ERROR_COPY}
                  </p>
                )}
              </TableCell>
              <TableCell className="align-top whitespace-nowrap">
                <TimestampCell value={run.created_at} />
              </TableCell>
              <TableCell className="align-top whitespace-nowrap">
                <TimestampCell value={run.started_at} />
              </TableCell>
              <TableCell className="align-top whitespace-nowrap">
                <TimestampCell value={run.finished_at} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
