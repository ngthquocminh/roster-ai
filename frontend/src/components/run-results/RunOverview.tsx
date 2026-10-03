import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { formatHours, formatPct, hoursByDay, summarizeCoverage } from "@/lib/coverageStats";

type Candidate = NonNullable<ScheduleRunResult["candidate"]>;

function Bar({ label, value, max, text }: Readonly<{ label: string; value: number; max: number; text: string }>) {
  const width = max > 0 ? Math.max(2, Math.min(100, (value / max) * 100)) : 0;
  return (
    <li className="grid grid-cols-[6.5rem_1fr_auto] items-center gap-3 text-sm">
      <span className="truncate">{label}</span>
      <span aria-hidden="true" className="h-3 rounded bg-muted"><span className="block h-3 rounded bg-primary" style={{ width: `${width}%` }} /></span>
      <span className="tabular-nums text-muted-foreground">{text}</span>
    </li>
  );
}

function Kpi({ label, value }: Readonly<{ label: string; value: string }>) {
  return <div className="rounded-xl border p-4"><dt className="text-sm text-muted-foreground">{label}</dt><dd className="mt-1 text-2xl font-semibold tabular-nums">{value}</dd></div>;
}

export function RunOverview({ candidate, candidateVersionId, baselineVersion, stale, onRequestApproval, requestPending, requestError, pendingApproval, approvalsUnavailable = false }: Readonly<{
  candidate: Candidate;
  candidateVersionId: string;
  baselineVersion: string | null;
  stale: boolean;
  onRequestApproval: () => void;
  requestPending: boolean;
  requestError: boolean;
  pendingApproval: boolean;
  /** The approvals read failed, so pending-state is unknown rather than absent. */
  approvalsUnavailable?: boolean;
}>) {
  const { metrics } = candidate;
  const coverage = summarizeCoverage(metrics);
  const days = hoursByDay(candidate.assignments);
  const maxDayHours = Math.max(0, ...days.map((d) => d.hours));
  const maxBucket = Math.max(0, ...coverage.buckets.map((b) => b.count));

  return (
    <section aria-labelledby="run-overview-heading" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-xl font-semibold" id="run-overview-heading">Schedule overview</h3>
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            <div className="flex items-center gap-2"><dt className="text-muted-foreground">Candidate version</dt><dd><IdentifierCopyButton identifierType="candidate version" value={candidateVersionId} /></dd></div>
            <div className="flex items-center gap-2"><dt className="text-muted-foreground">Baseline version</dt><dd>{baselineVersion ? <IdentifierCopyButton identifierType="baseline version" value={baselineVersion} /> : "No baseline version"}</dd></div>
          </dl>
        </div>
        <div className="space-y-1">
          <Button className="min-h-11" disabled={stale || pendingApproval || requestPending} onClick={onRequestApproval} type="button" variant="outline">Request approval</Button>
          {stale ? <p className="text-xs text-muted-foreground">Comparison is stale — refresh before requesting approval.</p> : null}
          {/* Text, never colour alone (EXPERIENCE.md Accessibility Floor); the
              unknown case says so rather than borrowing the pending copy —
              "already pending" would be a claim we cannot support when the read
              failed. */}
          {approvalsUnavailable ? <p className="text-xs text-muted-foreground">Existing approvals couldn&apos;t be loaded — reload before requesting approval.</p> : null}
          {pendingApproval && !approvalsUnavailable ? <p className="text-xs text-muted-foreground">A decision is already pending.</p> : null}
          {requestError ? <InlineAlert title="Approval request not created" description="Try again after refreshing the comparison." variant="destructive" /> : null}
        </div>
      </div>

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <Kpi label="Coverage" value={formatPct(coverage.coveragePct)} />
        <Kpi label="Under-served intervals" value={`${coverage.unresolvedCount} / ${coverage.intervalCount}`} />
        <Kpi label="Assignments" value={String(metrics.assignment_count)} />
        <Kpi label="Workers scheduled" value={String(metrics.member_count)} />
        <Kpi label="Total cost" value={metrics.total_cost.toFixed(2)} />
        <Kpi label="Overtime" value={formatHours(metrics.overtime_minutes)} />
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        <section aria-labelledby="coverage-by-function-heading" className="rounded-xl border p-4">
          <h4 className="font-semibold" id="coverage-by-function-heading">Coverage by function</h4>
          {coverage.byFunction.length ? (
            <ul aria-label="Coverage by function" className="mt-3 space-y-2">
              {coverage.byFunction.map((f) => <Bar key={f.name} label={f.name} max={100} text={`${formatPct(f.pct)} · ${formatHours(f.servedMinutes)} of ${formatHours(f.requiredMinutes)}`} value={f.pct ?? 0} />)}
            </ul>
          ) : <p className="mt-3 text-sm text-muted-foreground">No demand to cover.</p>}
        </section>

        <section aria-labelledby="hours-by-day-heading" className="rounded-xl border p-4">
          <h4 className="font-semibold" id="hours-by-day-heading">Scheduled hours by day</h4>
          {days.length ? (
            <ul aria-label="Scheduled hours by day" className="mt-3 space-y-2">
              {days.map((d) => <Bar key={d.day} label={`Day ${d.day}`} max={maxDayHours} text={`${d.hours.toFixed(1)} h`} value={d.hours} />)}
            </ul>
          ) : <p className="mt-3 text-sm text-muted-foreground">No assignments.</p>}
        </section>
      </div>

      <section aria-labelledby="unresolved-gaps-heading" className="rounded-xl border p-4">
        <h4 className="font-semibold" id="unresolved-gaps-heading">Unresolved gaps</h4>
        {coverage.unresolvedCount === 0 ? (
          <p className="mt-2 text-sm">No unresolved gaps — all {coverage.intervalCount} demand intervals are fully covered.</p>
        ) : (
          <div className="mt-3 grid gap-4 lg:grid-cols-2">
            <div className="space-y-3">
              <p className="text-sm">
                <strong>{coverage.unresolvedCount}</strong> of {coverage.intervalCount} demand intervals ({formatPct((coverage.unresolvedCount / coverage.intervalCount) * 100)}) are under-served,
                {" "}<strong>{formatHours(coverage.shortfallMinutes)}</strong> short in total.
              </p>
              <ul aria-label="Gaps by size" className="space-y-2">
                {coverage.buckets.map((b) => <Bar key={b.label} label={b.label} max={maxBucket} text={String(b.count)} value={b.count} />)}
              </ul>
            </div>
            <div>
              <p className="text-sm font-medium">Largest gaps</p>
              <ol aria-label="Largest gaps" className="mt-2 space-y-1 text-sm">
                {coverage.worst.map((g) => (
                  <li className="flex flex-wrap items-center justify-between gap-2" key={g.id}>
                    <IdentifierCopyButton identifierType="demand interval" value={g.id} />
                    <span className="tabular-nums text-muted-foreground">short {Math.round(g.shortfallMinutes)} min ({Math.round(g.servedMinutes)} of {Math.round(g.requiredMinutes)})</span>
                  </li>
                ))}
              </ol>
            </div>
          </div>
        )}
      </section>
    </section>
  );
}
