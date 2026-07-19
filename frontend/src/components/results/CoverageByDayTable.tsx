/**
 * D-05/RES-01 — the by-day coverage breakdown, by-day only (never
 * duplicating the demand-vs-served chart's by-function numbers). Reuses
 * RunHistoryTable's shadcn Table composition, dropping the scroll
 * container, row-click navigation, and loading/error/empty state machine —
 * this table renders synchronously from an already-loaded RunResult, no
 * independent query of its own.
 *
 * `coverage_by_day` keys are 0-indexed ("0".."6"); rendered 1-indexed via
 * `Number(dayKey) + 1` to match ScheduleTable's formatShiftWindow "Day N"
 * convention (RESEARCH.md Pitfall 2) — the same calendar day must read
 * identically in both tables. A null per-day value renders the literal
 * "Not computed" (plain text, no tooltip — that granularity is reserved for
 * the coverage stat row's D-07 tooltip treatment).
 *
 * Values are fractions in [0, 1] per docs/API.md ("day index (string) ->
 * fraction covered (0-1)"), matching CoverageStat.pct on the backend — scale
 * to a percentage for display, never render the raw fraction with a bare "%".
 */
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";

function formatCoveragePct(value: number): string {
  return `${Number((value * 100).toFixed(1))}%`;
}

export function CoverageByDayTable({
  coverage_by_day,
}: {
  coverage_by_day: Record<string, number | null>;
}) {
  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Day</TableHead>
          <TableHead>Coverage %</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {Object.entries(coverage_by_day).map(([dayKey, value]) => (
          <TableRow key={dayKey}>
            <TableCell>{`Day ${Number(dayKey) + 1}`}</TableCell>
            <TableCell>
              {value == null ? "Not computed" : formatCoveragePct(value)}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
