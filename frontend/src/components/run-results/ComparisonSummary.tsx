import type { ScheduleRunResult } from "@/api/scheduleRuns";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import { Button } from "@/components/ui/button";
import { InlineAlert } from "@/components/primitives/InlineAlert";

type Comparison = NonNullable<ScheduleRunResult["comparison"]>;
type Pair = [string, number];

function sum(values: Pair[]): number {
  // An empty tuple is a real zero (no demand rows), not "not computed" --
  // `calculate_candidate_metrics` always populates this field when a
  // comparison exists, so there is no absent-data case to distinguish here.
  return values.reduce((total, [, value]) => total + value, 0);
}

function delta(candidate: number | null, baseline: number | null): string {
  return candidate === null || baseline === null ? "Not computed" : (candidate - baseline).toFixed(2);
}

function IdList({ label, values }: Readonly<{ label: string; values: string[] }>) {
  return <div><dt className="text-muted-foreground">{label}</dt><dd>{values.length ? values.join(", ") : "None"}</dd></div>;
}

export function ComparisonSummary({ comparison, onRequestApproval, requestPending, requestError, pendingApproval, approvalsUnavailable = false }: Readonly<{
  comparison: Comparison;
  onRequestApproval: () => void;
  requestPending: boolean;
  requestError: boolean;
  pendingApproval: boolean;
  /** The approvals read failed, so pending-state is unknown rather than absent. */
  approvalsUnavailable?: boolean;
}>) {
  const candidate = comparison.candidate_metrics;
  const baseline = comparison.baseline_metrics;
  const objectiveNames = Array.from(new Set([
    ...candidate.objective_components.map(([name]) => name),
    ...baseline.objective_components.map(([name]) => name),
  ])).sort();
  const candidateObjectives = new Map(candidate.objective_components);
  const baselineObjectives = new Map(baseline.objective_components);

  return (
    <section aria-labelledby="comparison-heading" className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-xl font-semibold" id="comparison-heading">Candidate comparison</h3>
        <div className="space-y-1">
          <Button className="min-h-11" disabled={comparison.stale || pendingApproval || requestPending} onClick={onRequestApproval} type="button" variant="outline">Request approval</Button>
          {comparison.stale ? <p className="text-xs text-muted-foreground">Comparison is stale — refresh before requesting approval.</p> : null}
          {/* Text, never colour alone (EXPERIENCE.md Accessibility Floor), and
              the unknown case says so rather than borrowing the pending copy —
              "already pending" would be a claim we cannot support when the read
              failed. */}
          {approvalsUnavailable ? <p className="text-xs text-muted-foreground">Existing approvals couldn&apos;t be loaded — reload before requesting approval.</p> : null}
          {pendingApproval && !approvalsUnavailable ? <p className="text-xs text-muted-foreground">A decision is already pending.</p> : null}
          {requestError ? <InlineAlert title="Approval request not created" description="Try again after refreshing the comparison." variant="destructive" /> : null}
        </div>
      </div>

      {comparison.stale ? <InlineAlert title="Historical comparison" description={`Expected baseline ${comparison.expected_baseline_schedule_version ?? "none"}; current baseline ${comparison.current_baseline_schedule_version ?? "none"}. The frozen numbers remain visible below.`} /> : null}

      <dl className="grid gap-4 rounded-xl border p-4 md:grid-cols-2">
        <div><dt className="text-muted-foreground">Candidate version</dt><dd><IdentifierCopyButton identifierType="candidate version" value={comparison.candidate_schedule_version_id} /></dd></div>
        <div><dt className="text-muted-foreground">Baseline version</dt><dd>{comparison.expected_baseline_schedule_version ? <IdentifierCopyButton identifierType="baseline version" value={comparison.expected_baseline_schedule_version} /> : "No baseline version"}</dd></div>
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border p-4" aria-labelledby="assignment-diff-heading">
          <h4 className="font-semibold" id="assignment-diff-heading">Assignment changes</h4>
          <dl className="mt-3 grid gap-2 text-sm sm:grid-cols-2">
            <IdList label="Workers added" values={comparison.assignment_diff.added_worker_ids} />
            <IdList label="Workers removed" values={comparison.assignment_diff.removed_worker_ids} />
            <IdList label="Shifts added" values={comparison.assignment_diff.added_shift_ids} />
            <IdList label="Shifts removed" values={comparison.assignment_diff.removed_shift_ids} />
            <IdList label="Tasks added" values={comparison.assignment_diff.added_task_ids} />
            <IdList label="Tasks removed" values={comparison.assignment_diff.removed_task_ids} />
          </dl>
        </section>

        <section className="rounded-xl border p-4" aria-labelledby="metric-delta-heading">
          <h4 className="font-semibold" id="metric-delta-heading">Metric deltas</h4>
          <dl className="mt-3 grid gap-2 text-sm">
            <div><dt>Coverage required delta</dt><dd>{delta(sum(candidate.interval_coverage_required_minutes), sum(baseline.interval_coverage_required_minutes))}</dd></div>
            <div><dt>Coverage served delta</dt><dd>{delta(sum(candidate.interval_coverage_served_minutes), sum(baseline.interval_coverage_served_minutes))}</dd></div>
            <div><dt>Overtime delta</dt><dd>{delta(candidate.overtime_minutes, baseline.overtime_minutes)}</dd></div>
            <div><dt>Cost delta</dt><dd>{delta(candidate.total_cost, baseline.total_cost)}</dd></div>
            {objectiveNames.map((name) => <div key={name}><dt>{name} objective delta</dt><dd>{delta(candidateObjectives.get(name) ?? null, baselineObjectives.get(name) ?? null)}</dd></div>)}
          </dl>
        </section>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border p-4"><h4 className="font-semibold">Candidate constraints</h4><ul className="mt-2 list-disc pl-5 text-sm">{comparison.candidate_constraint_results.length ? comparison.candidate_constraint_results.map((item) => <li key={item.constraint_id}>{item.constraint_type}: {item.satisfied ? "Satisfied" : "Not satisfied"}</li>) : <li>Not computed</li>}</ul></section>
        <section className="rounded-xl border p-4"><h4 className="font-semibold">Baseline hard constraints</h4><ul className="mt-2 list-disc pl-5 text-sm">{comparison.baseline_hard_constraint_results.length ? comparison.baseline_hard_constraint_results.map((item) => <li key={item.constraint_id}>{item.constraint_type}: {item.satisfied ? "Satisfied" : "Not satisfied"}</li>) : <li>Not computed</li>}</ul></section>
      </div>

      <section className="rounded-xl border p-4"><h4 className="font-semibold">Warnings</h4><ul className="mt-2 list-disc pl-5 text-sm">{comparison.warnings.length ? comparison.warnings.map((warning) => <li key={warning}>{warning}</li>) : <li>None</li>}</ul></section>
      <section className="rounded-xl border p-4"><h4 className="font-semibold">Unresolved gaps</h4><ul className="mt-2 list-disc pl-5 text-sm">{comparison.unresolved_gap_record_ids.length ? comparison.unresolved_gap_record_ids.map((id) => <li key={id}>{id}</li>) : <li>None</li>}</ul></section>
    </section>
  );
}
