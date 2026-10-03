import { useMemo, useState } from "react";

import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useTaskNameMap, useWorkerNameMap } from "@/hooks/useScenarioProjection";
import { formatMinuteWindow } from "@/lib/formatShiftWindow";

type Assignment = NonNullable<ScheduleRunResult["candidate"]>["assignments"][number];

export const SCHEDULE_PAGE_SIZE = 25;

function duration(a: Assignment): string {
  return `${((a.end_minute - a.start_minute) / 60).toFixed(1)} h`;
}

export function CandidateScheduleTable({ assignments, scenarioId }: Readonly<{ assignments: Assignment[]; scenarioId: string }>) {
  const workerNames = useWorkerNameMap(scenarioId);
  const taskNames = useTaskNameMap(scenarioId);
  const [page, setPage] = useState(0);

  const sorted = useMemo(() => {
    const nameOf = (id: string) => workerNames.data?.get(id) ?? id;
    return [...assignments].sort((a, b) =>
      nameOf(a.worker_id).localeCompare(nameOf(b.worker_id)) || a.start_minute - b.start_minute || a.record_id.localeCompare(b.record_id));
  }, [assignments, workerNames.data]);

  const pageCount = Math.max(1, Math.ceil(sorted.length / SCHEDULE_PAGE_SIZE));
  const current = Math.min(page, pageCount - 1);
  const rows = sorted.slice(current * SCHEDULE_PAGE_SIZE, (current + 1) * SCHEDULE_PAGE_SIZE);

  return (
    <section aria-labelledby="candidate-schedule-heading" className="rounded-xl border p-4">
      <h3 className="font-semibold" id="candidate-schedule-heading">Candidate schedule</h3>
      {sorted.length === 0 ? <p className="mt-2 text-sm">No assignments</p> : (
        <>
          <Table className="mt-3">
            <TableHeader>
              <TableRow>
                <TableHead scope="col">Worker</TableHead>
                <TableHead scope="col">Task</TableHead>
                <TableHead scope="col">Shift</TableHead>
                <TableHead scope="col">Window</TableHead>
                <TableHead scope="col">Duration</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((a) => (
                <TableRow key={a.record_id}>
                  <TableCell><IdentifierCopyButton identifierType="Worker ID" label={workerNames.data?.get(a.worker_id)} value={a.worker_id} /></TableCell>
                  <TableCell><IdentifierCopyButton identifierType="Task ID" label={taskNames.data?.get(a.task_id)} value={a.task_id} /></TableCell>
                  <TableCell>{a.shift_id ? <IdentifierCopyButton identifierType="Shift ID" value={a.shift_id} /> : "—"}</TableCell>
                  <TableCell>{formatMinuteWindow(a.start_minute, a.end_minute)}</TableCell>
                  <TableCell className="tabular-nums">{duration(a)}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {pageCount > 1 ? (
            <nav aria-label="Schedule pages" className="mt-3 flex items-center justify-between gap-3 text-sm">
              <span>{current * SCHEDULE_PAGE_SIZE + 1}–{current * SCHEDULE_PAGE_SIZE + rows.length} of {sorted.length}</span>
              <div className="flex gap-2">
                <Button disabled={current === 0} onClick={() => setPage(current - 1)} type="button" variant="outline">Previous</Button>
                <Button disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)} type="button" variant="outline">Next</Button>
              </div>
            </nav>
          ) : null}
        </>
      )}
    </section>
  );
}
