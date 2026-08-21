import { useEffect, useId, useRef, useState } from "react";

import {
  toConstraintInput,
  type ProposalConstraintInput,
} from "@/api/proposals";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useProposal } from "@/hooks/useProposal";
import { useRejectProposal } from "@/hooks/useRejectProposal";
import { useReviseProposal } from "@/hooks/useReviseProposal";
import { useStartScheduleRun } from "@/hooks/useStartScheduleRun";
import { getErrorCode, getErrorStatus } from "@/lib/errors";

type NumericKey = "n" | "factor" | "max_hours" | "start_minute";

const PARAMETER: Partial<
  Record<ProposalConstraintInput["kind"], { key: NumericKey; label: string }>
> = {
  set_min_workers_per_task: { key: "n", label: "Minimum workers" },
  scale_demand: { key: "factor", label: "Demand factor" },
  lock_worker_shift: { key: "start_minute", label: "Start minute" },
  set_max_hours: { key: "max_hours", label: "Maximum hours" },
  // `exclude_worker_from_task` is absent on purpose: it carries no numeric
  // argument. A placeholder entry here would be a lookup that must never be
  // looked up, and the next editor removing its guard would bind an input to a
  // key the kind rejects.
};

function Identifier({ children }: Readonly<{ children: string }>) {
  return <code className="font-mono text-xs break-all">{children}</code>;
}

/**
 * Copy keyed on the RFC 7807 `code`, falling back to HTTP status.
 *
 * Status alone cannot separate these: the run command answers `stale_proposal`,
 * `stale_resource_version` and `idempotency_key_conflict` all as 409. Rendering
 * one message for all three told a planner holding a conflicting key to
 * "Refresh… then try again" — the one action that cannot help, because the key
 * is deliberately held across failures and a refreshed body only changes the
 * hash it conflicts on. `getErrorCode` already backs `EvidenceTargetPanel`.
 */
const CODE_MESSAGES: Readonly<Record<string, string>> = {
  stale_proposal:
    "This draft changed since you opened it. Refresh to see the current version, then try again.",
  stale_resource_version:
    "This draft changed since you opened it. Refresh to see the current version, then try again.",
  idempotency_key_conflict:
    "An earlier command with different values is still on record for this draft. Reload the page to start a fresh command.",
  site_concurrency_exhausted: "This site is at its run limit. Try again shortly.",
  proposal_not_found:
    "This draft is no longer available. Describe the change again to create a new one.",
  rejected_proposal:
    "This proposal was rejected, so it cannot be run. Describe the change again to create a new one.",
  scenario_unavailable:
    "The scenario could not be read just now. Try again shortly.",
  compute_not_granted:
    "Optimization is turned off for this site, so no run can be started.",
};

const STATUS_MESSAGES: Readonly<Record<number, string>> = {
  403: "Optimization is turned off for this site, so no run can be started.",
  409: "This draft changed since you opened it. Refresh to see the current version, then try again.",
  422: "That command was refused: check the values and try again.",
  429: "This site is at its run limit. Try again shortly.",
  503: "The scenario could not be read just now. Try again shortly.",
};

function commandMessage(error: unknown): string {
  const code = getErrorCode(error);
  if (code && code in CODE_MESSAGES) {
    return CODE_MESSAGES[code];
  }
  const status = getErrorStatus(error);
  if (status !== undefined && status in STATUS_MESSAGES) {
    return STATUS_MESSAGES[status];
  }
  return "That command did not complete. Try again.";
}

export function DraftCard({
  proposalId,
  consequenceSummary,
}: Readonly<{ proposalId: string; consequenceSummary?: string }>) {
  const query = useProposal(proposalId);
  const revision = useReviseProposal(proposalId);
  const rejection = useRejectProposal(proposalId);
  const run = useStartScheduleRun();
  const staleDescriptionId = useId();
  const runDescriptionId = `${staleDescriptionId}-run`;
  const [constraints, setConstraints] = useState<ProposalConstraintInput[]>([]);
  const [selected, setSelected] = useState("0");
  // Which server version the local edits were seeded from. Re-seeding on every
  // `query.data` identity change discarded whatever the planner had typed the
  // moment a background refetch landed (TanStack refetches on window focus by
  // default), with no indication that it had happened.
  const seededVersion = useRef<string | null>(null);

  useEffect(() => {
    if (!query.data) return;
    if (seededVersion.current === query.data.proposal_version_id) return;
    seededVersion.current = query.data.proposal_version_id;
    setConstraints(query.data.constraints.map(toConstraintInput));
    setSelected("0");
  }, [query.data]);

  // The persisted activity already carries the application-composed summary, so
  // the immutable audit record can be shown immediately rather than replaced by
  // a spinner until a network round trip completes. `DraftActivityV1` persists
  // it precisely so the timeline can render a reference (Decision 6).
  if (query.isPending) {
    return (
      <Card aria-label="Draft proposal" role="region">
        <CardHeader>
          <CardTitle>Draft — no baseline change</CardTitle>
          {consequenceSummary ? (
            <CardDescription>{consequenceSummary}</CardDescription>
          ) : null}
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">Loading draft proposal…</p>
        </CardContent>
      </Card>
    );
  }
  if (query.isError || !query.data) {
    return (
      <InlineAlert
        action={<Button className="min-h-11" onClick={() => query.refetch()} variant="outline">Retry</Button>}
        description={
          getErrorStatus(query.error) === 503
            ? "The proposal exists but its scenario could not be read."
            : consequenceSummary
              ? `The proposal could not be loaded. It recorded: ${consequenceSummary}`
              : "The proposal could not be loaded."
        }
        title="Draft unavailable"
        variant="destructive"
      />
    );
  }

  const proposal = query.data;
  const rejected = proposal.state === "rejected";
  const selectedIndex = Math.min(Number(selected), Math.max(constraints.length - 1, 0));
  const current = constraints[selectedIndex];
  const parameter = current ? PARAMETER[current.kind] : undefined;
  const mutationPending = revision.isPending || rejection.isPending || run.isPending;
  const runDisabled = proposal.stale || rejected || mutationPending;
  const runExplanation = [
    "Running optimization starts a bounded computation and does not change the baseline.",
    proposal.stale ? "Refresh the proposal before running optimization." : null,
    rejected ? "A rejected proposal cannot be run." : null,
    mutationPending ? "Wait for the current proposal command to finish." : null,
  ].filter(Boolean).join(" ");
  // Most recent failure wins, not a fixed order. A fixed chain meant a revise
  // that failed once — and whose error TanStack retains until that same
  // mutation is re-fired — masked every later run failure, so the site-limit
  // message could never be seen after any failed revise.
  // The acknowledgement is only true of the version the run was started from.
  // `run.data` alone survives a successful revise — TanStack clears it only
  // when the run mutation itself is re-fired — so the live region kept
  // announcing a run accepted for version 1 beside a draft now at version 2.
  // `run.variables` carries the body that produced `run.data`, so the two
  // cannot drift apart the way a separately-tracked ref could.
  const acknowledged =
    run.data &&
    run.variables?.expected_resource_version === proposal.resource_version
      ? run.data
      : null;
  const commandError = [revision, rejection, run]
    .filter((mutation) => mutation.error)
    .sort((a, b) => (b.submittedAt ?? 0) - (a.submittedAt ?? 0))
    .map((mutation) => mutation.error)
    .at(0) ?? null;
  const updateNumber = (key: NumericKey | "end_minute", raw: string) => {
    const value = raw === "" ? null : Number(raw);
    setConstraints((existing) => existing.map((constraint, index) =>
      index === selectedIndex ? { ...constraint, [key]: value } : constraint,
    ));
  };

  return (
    <Card aria-label="Draft proposal" role="region">
      <CardHeader>
        <CardTitle>Draft — no baseline change</CardTitle>
        <CardDescription>{proposal.consequence_summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Both states can hold at once, so both are announced. Testing `stale`
            first and returning made the rejected notice unreachable whenever a
            scenario reimport followed a rejection. */}
        {proposal.stale ? (
          <div aria-label="Draft is stale" className="rounded-lg border border-destructive/40 p-3" role="status">
            <p className="font-medium text-destructive">Draft is stale</p>
            <p className="text-sm text-muted-foreground" id={staleDescriptionId}>
              The scenario version changed. Refresh before revising this proposal.
            </p>
          </div>
        ) : null}
        {rejected ? (
          <div aria-label="Draft is rejected" className="rounded-lg border p-3" role="status">
            <p className="font-medium">This proposal was rejected.</p>
            <p className="text-sm text-muted-foreground">
              A rejected draft is final. Describe the change again to create a new one.
            </p>
          </div>
        ) : null}

        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-muted-foreground">Expected scenario version</dt><dd><Identifier>{proposal.scenario_version_id}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Current scenario version</dt><dd><Identifier>{proposal.current_scenario_version_id}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Expected baseline version</dt><dd><Identifier>{proposal.expected_baseline_schedule_version ?? "No baseline version"}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Proposal version</dt><dd><Identifier>{proposal.proposal_version_id}</Identifier></dd></div>
        </dl>

        <section aria-labelledby={`${staleDescriptionId}-entities`}>
          <h3 className="text-sm font-medium" id={`${staleDescriptionId}-entities`}>Resolved entities</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {proposal.resolved_entities.map((entity) => (
              <li key={`${entity.group}:${entity.record_id}`}>
                {entity.label} · <Identifier>{entity.record_id}</Identifier> · {entity.group}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby={`${staleDescriptionId}-constraints`} className="space-y-2">
          <h3 className="text-sm font-medium" id={`${staleDescriptionId}-constraints`}>Constraints and objectives</h3>
          {/* Server-composed descriptions, always. The card never echoes a
              description back on revision, so this text cannot drift from the
              argument it describes. */}
          <ul className="list-disc space-y-1 pl-5 text-sm">
            {proposal.constraints.map((constraint, index) => <li key={`${constraint.kind}-${index}`}>{constraint.description}</li>)}
          </ul>
          {constraints.length && !rejected ? (
            <div className="grid gap-3 sm:grid-cols-2">
              <label className="space-y-1 text-sm">
                <span>Constraint to revise</span>
                <Select onValueChange={setSelected} value={String(selectedIndex)}>
                  <SelectTrigger className="min-h-11 w-full" aria-label="Constraint to revise"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {proposal.constraints.map((constraint, index) => (
                      <SelectItem key={`${constraint.kind}-${index}`} value={String(index)}>{constraint.description}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </label>
              {current && parameter ? (
                <label className="space-y-1 text-sm">
                  <span>{parameter.label}</span>
                  <Input
                    aria-label={parameter.label}
                    className="min-h-11"
                    disabled={proposal.stale}
                    min="0"
                    onChange={(event) => updateNumber(parameter.key, event.target.value)}
                    type="number"
                    value={String(current[parameter.key] ?? "")}
                  />
                </label>
              ) : null}
              {current?.kind === "lock_worker_shift" ? (
                <label className="space-y-1 text-sm">
                  <span>End minute</span>
                  <Input aria-label="End minute" className="min-h-11" disabled={proposal.stale} min="0" onChange={(event) => updateNumber("end_minute", event.target.value)} type="number" value={String(current.end_minute ?? "")} />
                </label>
              ) : null}
            </div>
          ) : null}
        </section>

        <section aria-labelledby={`${staleDescriptionId}-locks`}>
          <h3 className="text-sm font-medium" id={`${staleDescriptionId}-locks`}>Preserved locks</h3>
          {proposal.preserved_locks.length ? (
            <ul className="mt-1 space-y-1 text-sm">{proposal.preserved_locks.map((lock) => <li key={lock.record_id}><Identifier>{lock.record_id}</Identifier> · {lock.scope} · {lock.target_ref}</li>)}</ul>
          ) : <p className="text-sm text-muted-foreground">No existing locks.</p>}
        </section>
      </CardContent>
      <CardFooter className="block space-y-3">
        {commandError ? (
          <InlineAlert
            description={commandMessage(commandError)}
            title="Command not applied"
            variant="destructive"
          />
        ) : null}
        {acknowledged ? (
          <div
            aria-label="Optimization queued"
            aria-live="polite"
            className="rounded-lg border p-3 text-sm"
            role="status"
          >
            Run <Identifier>{acknowledged.schedule_run_id}</Identifier> was accepted with status{" "}
            <span className="font-medium">{acknowledged.status}</span>.
          </div>
        ) : null}
        <div className="space-y-2">
          <p className="text-sm text-muted-foreground" id={runDescriptionId}>
            {runExplanation}
          </p>
          <Button
            aria-describedby={runDescriptionId}
            className="min-h-11"
            disabled={runDisabled}
            onClick={() => run.mutate({
              proposal_id: proposal.proposal_id,
              expected_resource_version: proposal.resource_version,
            })}
            type="button"
            variant="secondary"
          >Run optimization</Button>
        </div>
        {rejected ? null : (
          <>
            {/* Revise stays MOUNTED and disabled when stale, carrying the
                explanation. Rendering a separate screen-reader-only button
                instead left the real control unrendered and satisfied the
                accessibility assertions against a decoy that could never be
                enabled. */}
            <div>
              <Button
                aria-describedby={proposal.stale ? staleDescriptionId : undefined}
                className="min-h-11"
                disabled={proposal.stale || mutationPending}
                onClick={() => revision.mutate({ constraints, expected_resource_version: proposal.resource_version })}
                type="button"
              >Revise proposal</Button>
            </div>
            <Separator />
            {/* Reject is available while stale, deliberately: it changes no
                baseline and is the only terminal path a stale draft has. */}
            <div>
              <Button className="min-h-11" disabled={mutationPending} onClick={() => rejection.mutate({ expected_resource_version: proposal.resource_version })} type="button" variant="destructive">Reject proposal</Button>
            </div>
            {proposal.stale ? (
              <div>
                <Button className="min-h-11" onClick={() => query.refetch()} type="button" variant="outline">Refresh proposal</Button>
              </div>
            ) : null}
          </>
        )}
      </CardFooter>
    </Card>
  );
}
