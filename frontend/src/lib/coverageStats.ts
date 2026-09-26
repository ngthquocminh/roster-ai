import type { components } from "@/api/schema";

type MetricSet = components["schemas"]["MetricSetOut"];

export type GapBucket = { label: string; count: number };
export type WorstGap = { id: string; requiredMinutes: number; servedMinutes: number; shortfallMinutes: number };
export type FunctionCoverage = { name: string; requiredMinutes: number; servedMinutes: number; pct: number | null };

export type CoverageSummary = {
  requiredMinutes: number;
  servedMinutes: number;
  /** Null when nothing is required, so callers render "—" instead of NaN. */
  coveragePct: number | null;
  intervalCount: number;
  unresolvedCount: number;
  shortfallMinutes: number;
  buckets: GapBucket[];
  worst: WorstGap[];
  byFunction: FunctionCoverage[];
};

const TOP_N = 5;
const BUCKET_LABELS = ["Under 30 min", "30–60 min", "1–2 h", "Over 2 h"] as const;

function bucketIndex(shortfall: number): number {
  if (shortfall < 30) return 0;
  if (shortfall < 60) return 1;
  if (shortfall <= 120) return 2;
  return 3;
}

function pct(served: number, required: number): number | null {
  return required > 0 ? Math.min(100, (served / required) * 100) : null;
}

// Same rule as the server's `unresolved_gap_record_ids` (served < required),
// applied to the same interval metrics, so counts match that list.
export function summarizeCoverage(metrics: MetricSet): CoverageSummary {
  const served = new Map(metrics.interval_coverage_served_minutes);
  const buckets = BUCKET_LABELS.map((label): GapBucket => ({ label, count: 0 }));
  const gaps: WorstGap[] = [];
  let requiredMinutes = 0;
  let servedMinutes = 0;
  let shortfallMinutes = 0;

  for (const [id, required] of metrics.interval_coverage_required_minutes) {
    const got = served.get(id) ?? 0;
    requiredMinutes += required;
    servedMinutes += Math.min(got, required);
    if (got < required) {
      const shortfall = required - got;
      shortfallMinutes += shortfall;
      buckets[bucketIndex(shortfall)].count += 1;
      gaps.push({ id, requiredMinutes: required, servedMinutes: got, shortfallMinutes: shortfall });
    }
  }

  gaps.sort((a, b) => b.shortfallMinutes - a.shortfallMinutes || a.id.localeCompare(b.id));

  const functionServed = new Map(metrics.function_coverage_served_minutes);
  const byFunction = metrics.function_coverage_required_minutes
    .map(([name, required]): FunctionCoverage => {
      const got = functionServed.get(name) ?? 0;
      return { name, requiredMinutes: required, servedMinutes: got, pct: pct(got, required) };
    })
    .sort((a, b) => a.name.localeCompare(b.name));

  return {
    requiredMinutes,
    servedMinutes,
    coveragePct: pct(servedMinutes, requiredMinutes),
    intervalCount: metrics.interval_coverage_required_minutes.length,
    unresolvedCount: gaps.length,
    shortfallMinutes,
    buckets,
    worst: gaps.slice(0, TOP_N),
    byFunction,
  };
}

export function formatHours(minutes: number): string {
  return `${(minutes / 60).toFixed(1)} h`;
}

export function formatPct(value: number | null): string {
  return value === null ? "—" : `${value.toFixed(1)}%`;
}

/** Scheduled hours per 1-indexed day; an assignment crossing midnight is split at the boundary. */
export function hoursByDay(assignments: ReadonlyArray<{ start_minute: number; end_minute: number }>): Array<{ day: number; hours: number }> {
  const minutes = new Map<number, number>();
  for (const { start_minute: start, end_minute: end } of assignments) {
    let cursor = start;
    while (cursor < end) {
      const day = Math.floor(cursor / 1440);
      const dayEnd = (day + 1) * 1440;
      const slice = Math.min(end, dayEnd) - cursor;
      minutes.set(day + 1, (minutes.get(day + 1) ?? 0) + slice);
      cursor += slice;
    }
  }
  return [...minutes.entries()].sort((a, b) => a[0] - b[0]).map(([day, m]) => ({ day, hours: m / 60 }));
}
