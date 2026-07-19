/**
 * RES-03 schedule table (D-08, D-09, D-10) — renders `RunResult.schedule` as
 * a scrollable table, reusing `RunHistoryTable.tsx`'s exact
 * `max-h-[420px] overflow-y-auto rounded-md border border-border` container
 * verbatim (D-08).
 *
 * Server order only — this component performs NO client-side sort or
 * filter over the schedule rows (D-09), matching `RunHistoryTable.tsx`'s
 * own established precedent of stating this rule in prose, not just code.
 *
 * `member_name`/`task_id`/`function` cell values render only as plain JSX
 * text children (T-04-01) — React's default text-node escaping is the
 * complete mitigation; this file contains no raw-HTML injection sink (the
 * plan's acceptance check greps for the literal sink name and expects a
 * zero count, so it is deliberately not spelled out here).
 *
 * Unlike `RunHistoryTable`, rows here are terminal (no row-click
 * navigation) and there is no independent loading/error/empty state
 * machine tied to a query — the parent `ResultsView` (plan 04-07) already
 * gates rendering on `useRunResult`'s success state before mounting this
 * component; the only local state this file owns is the defensive
 * zero-shifts empty state below.
 */
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { formatShiftWindow } from "@/lib/formatShiftWindow";
import type { ScheduleRow } from "@/api/results";

const EMPTY_SCHEDULE_COPY = "No shifts were scheduled for this run.";

export function ScheduleTable({ schedule }: { schedule: ScheduleRow[] }) {
  if (schedule.length === 0) {
    return (
      <div className="flex flex-col items-center gap-2 py-16 text-center">
        <p className="text-sm leading-[1.5] text-muted-foreground">
          {EMPTY_SCHEDULE_COPY}
        </p>
      </div>
    );
  }

  return (
    <div className="max-h-[420px] overflow-y-auto rounded-md border border-border">
      <Table className="table-fixed">
        <TableHeader>
          <TableRow>
            <TableHead className="w-[28%]">Member</TableHead>
            <TableHead className="w-[24%]">Task</TableHead>
            <TableHead className="w-[20%]">Function</TableHead>
            <TableHead className="w-[28%]">Shift Window</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {/* Server order only — no .sort()/.filter() over `schedule` (D-09). */}
          {schedule.map((row) => (
            <TableRow key={`${row.shift_id}-${row.contact_id}-${row.task_id}`}>
              <TableCell className="align-top whitespace-normal">
                {row.member_name}
              </TableCell>
              <TableCell className="align-top whitespace-normal">
                {row.task_id}
              </TableCell>
              <TableCell className="align-top whitespace-normal">
                {row.function}
              </TableCell>
              <TableCell className="align-top whitespace-nowrap">
                {formatShiftWindow(row.start_h, row.end_h)}
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
