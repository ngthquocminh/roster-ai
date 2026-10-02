/**
 * The conversation's one working draft, reviewed and edited in place.
 *
 * Story 5.11 (UX-DR9 as amended, UX-DR25, UX-DR35): every constraint row is
 * editable, rows can be removed (never the last), Save changes / Cancel act on
 * the local list, Run optimization is disabled while edits are unsaved, Discard
 * asks for an inline two-step confirmation, and an ended draft is read-only
 * with one state line. The unsaved edits live in `ActivityTimeline` (or a local
 * fallback) so they survive this card moving to a newer activity (C8).
 */
import { useEffect, useId, useMemo, useRef, useState, type RefObject } from "react";

import type { Proposal, ProposalConstraintInput } from "@/api/proposals";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardFooter, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import { useProposal } from "@/hooks/useProposal";
import { useRejectProposal } from "@/hooks/useRejectProposal";
import { useReviseProposal } from "@/hooks/useReviseProposal";
import { useScenarioOverview } from "@/hooks/useScenarioProjection";
import { useStartScheduleRun } from "@/hooks/useStartScheduleRun";
import { getErrorCode, getErrorStatus } from "@/lib/errors";

import {
  rowsEqual,
  rowsFromProposal,
  stateLine,
  validateRow,
  type EditBuffer,
  type EditRow,
  type EditableField,
} from "./draftEdits";

/** Which editable inputs each kind shows, in order. */
const FIELDS: Partial<Record<ProposalConstraintInput["kind"], readonly { key: EditableField; label: string; step?: string }[]>> = {
  set_min_workers_per_task: [{ key: "n", label: "Minimum workers", step: "1" }],
  scale_demand: [{ key: "factor", label: "Demand factor", step: "any" }],
  set_max_hours: [{ key: "max_hours", label: "Maximum hours", step: "any" }],
  lock_worker_shift: [
    { key: "start_minute", label: "Start minute", step: "1" },
    { key: "end_minute", label: "End minute", step: "1" },
  ],
  // `exclude_worker_from_task` is absent on purpose: it carries no argument. A
  // placeholder entry would be a lookup that must never be looked up.
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
  // Reachable from revise, discard and run since Story 5.11 (C4): the router now
  // answers `rejected_proposal` for all three.
  rejected_proposal:
    "This proposal was rejected, so it cannot be changed or run. Describe the change again to create a new one.",
  applied_proposal:
    "This draft was applied to the baseline, so it cannot be changed or run. Describe the change again to start a new draft.",
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

const IN_FLIGHT_HINT = "Wait for the assistant to finish";

type DraftCardProps = Readonly<{
  proposalId: string;
  consequenceSummary?: string;
  /** An agent turn is running in this conversation: Save, Discard and Run wait. */
  agentTurnInFlight?: boolean;
  /**
   * Controlled edit buffer. `ActivityTimeline` owns it so unsaved edits survive
   * this card being unmounted and re-mounted on a newer activity (C8); a card
   * rendered without it keeps its own.
   */
  buffer?: EditBuffer | null;
  onBufferChange?: (buffer: EditBuffer | null) => void;
}>;

export function DraftCard({
  proposalId,
  consequenceSummary,
  agentTurnInFlight = false,
  buffer: controlledBuffer,
  onBufferChange,
}: DraftCardProps) {
  const query = useProposal(proposalId);
  const revision = useReviseProposal(proposalId);
  const rejection = useRejectProposal(proposalId);
  const run = useStartScheduleRun();
  const overview = useScenarioOverview(query.data?.scenario_id ?? "");
  const horizon = overview?.data?.horizon_minutes;
  const baseId = useId();
  const staleDescriptionId = `${baseId}-stale`;
  const runDescriptionId = `${baseId}-run`;
  const inFlightId = `${baseId}-inflight`;

  const [localBuffer, setLocalBuffer] = useState<EditBuffer | null>(null);
  const controlled = onBufferChange !== undefined;
  const buffer = controlled ? (controlledBuffer ?? null) : localBuffer;
  const setBuffer = controlled ? onBufferChange : setLocalBuffer;
  // The save acknowledgement is true only of the version it saved: kept with
  // that version's id so it disappears once the draft moves on, the same rule
  // as the run acknowledgement below (code review of story-5.11).
  const [saved, setSaved] = useState<{ versionId: string; ordinal: number | null } | null>(null);
  const [confirmingDiscard, setConfirmingDiscard] = useState(false);
  const keepRef = useRef<HTMLButtonElement>(null);
  const discardRef = useRef<HTMLButtonElement>(null);
  const returnFocusToDiscard = useRef(false);

  const proposal = query.data;
  const serverRows = useMemo(() => (proposal ? rowsFromProposal(proposal) : []), [proposal]);

  // A buffer whose rows already equal the server's carries nothing: the planner's
  // own save landed (possibly while this card was being re-mounted), or the
  // assistant made the same change. Drop it rather than reporting a phantom diff.
  useEffect(() => {
    if (buffer && proposal && rowsEqual(buffer.rows, serverRows)) setBuffer(null);
  }, [buffer, proposal, serverRows, setBuffer]);

  useEffect(() => {
    if (confirmingDiscard) keepRef.current?.focus();
    else if (returnFocusToDiscard.current) {
      returnFocusToDiscard.current = false;
      discardRef.current?.focus();
    }
  }, [confirmingDiscard]);

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
  if (query.isError || !proposal) {
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

  const ended = proposal.state !== "active";
  const rows: readonly EditRow[] = buffer?.rows ?? serverRows;
  const hasDifference = buffer !== null && !rowsEqual(buffer.rows, serverRows);
  const changedUnderEdits = hasDifference && buffer.baseVersionId !== proposal.proposal_version_id;
  const rowErrors = rows.map((row) => validateRow(row.input, horizon));
  const allValid = rowErrors.every((errors) => Object.keys(errors).length === 0);
  const mutationPending = revision.isPending || rejection.isPending || run.isPending;
  const editable = !ended && !proposal.stale;
  // Typing while a command is pending would be wiped by that command's success
  // (it clears the buffer), so the rows wait for it (code review of story-5.11).
  const rowsEditable = editable && !mutationPending;
  // `validateRow` skips the horizon bound when the horizon is unknown, so a lock
  // row cannot be judged until the scenario overview has loaded.
  const horizonKnown = horizon !== undefined
    || !rows.some((row) => row.input.kind === "lock_worker_shift");

  const canSave = editable && hasDifference && allValid && horizonKnown && !changedUnderEdits
    && !mutationPending && !agentTurnInFlight;
  const runDisabled = proposal.stale || ended || hasDifference || mutationPending || agentTurnInFlight;
  const runExplanation = [
    "Running optimization starts a bounded computation and does not change the baseline.",
    proposal.stale ? "Refresh the proposal before running optimization." : null,
    ended ? "An ended draft cannot be run." : null,
    hasDifference ? "Save or cancel your changes first." : null,
    agentTurnInFlight ? `${IN_FLIGHT_HINT}.` : null,
    mutationPending ? "Wait for the current proposal command to finish." : null,
  ].filter(Boolean).join(" ");

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
  // Most recent failure wins, not a fixed order. A fixed chain meant a revise
  // that failed once — and whose error TanStack retains until that same
  // mutation is re-fired — masked every later run failure.
  const commandError = [revision, rejection, run]
    .filter((mutation) => mutation.error)
    .sort((a, b) => (b.submittedAt ?? 0) - (a.submittedAt ?? 0))
    .map((mutation) => mutation.error)
    .at(0) ?? null;

  const commit = (next: readonly EditRow[]) => {
    const baseVersionId = buffer?.baseVersionId ?? proposal.proposal_version_id;
    setSaved(null);
    if (baseVersionId === proposal.proposal_version_id && rowsEqual(next, serverRows)) {
      setBuffer(null);
    } else {
      setBuffer({ baseVersionId, rows: next });
    }
  };
  const updateField = (index: number, key: EditableField, raw: string) => {
    const value = raw === "" ? null : Number(raw);
    commit(rows.map((row, position) => position === index
      ? { ...row, input: { ...row.input, [key]: Number.isNaN(value) ? null : value } }
      : row));
  };
  const removeRow = (index: number) => {
    if (rows.length <= 1) return;
    commit(rows.filter((_row, position) => position !== index));
  };
  const save = () => revision.mutate(
    {
      constraints: rows.map((row) => row.input),
      expected_resource_version: proposal.resource_version,
    },
    {
      onSuccess: (result) => {
        setBuffer(null);
        setSaved({ versionId: result.proposal_version_id, ordinal: result.version_ordinal ?? null });
      },
    },
  );
  const versionLabel = proposal.version_ordinal != null ? `v${proposal.version_ordinal}` : null;
  const savedLabel = saved && saved.versionId === proposal.proposal_version_id
    ? (saved.ordinal != null ? `Saved as v${saved.ordinal}` : "Saved")
    : null;
  // Load and Cancel start over from the server's version, so a revise error
  // about the abandoned edits is no longer true (code review of story-5.11).
  const resetEdits = () => {
    setSaved(null);
    setBuffer(null);
    revision.reset();
  };

  return (
    <Card aria-label="Draft proposal" role="region">
      <CardHeader>
        <div className="flex flex-wrap items-center gap-2">
          <CardTitle>Draft — no baseline change</CardTitle>
          <Badge variant={ended ? "outline" : proposal.stale ? "destructive" : "secondary"}>
            {stateLine(proposal)}
          </Badge>
        </div>
        <CardDescription>{proposal.consequence_summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* The stale notice belongs to an ACTIVE draft only: an ended draft
            offers no action for staleness to block, and its badge already says
            what it is (Decision 14). */}
        {!ended && proposal.stale ? (
          <div aria-label="Draft is stale" className="rounded-lg border border-destructive/40 p-3" role="status">
            <p className="font-medium text-destructive">Draft is stale</p>
            <p className="text-sm text-muted-foreground" id={staleDescriptionId}>
              The scenario version changed. Refresh before revising this proposal.
            </p>
          </div>
        ) : null}

        <dl className="grid gap-2 text-sm sm:grid-cols-2">
          <div><dt className="text-muted-foreground">Expected scenario version</dt><dd><Identifier>{proposal.scenario_version_id}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Current scenario version</dt><dd><Identifier>{proposal.current_scenario_version_id}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Expected baseline version</dt><dd><Identifier>{proposal.expected_baseline_schedule_version ?? "No baseline version"}</Identifier></dd></div>
          <div><dt className="text-muted-foreground">Proposal version</dt><dd><Identifier>{proposal.proposal_version_id}</Identifier></dd></div>
          {versionLabel ? (
            <div><dt className="text-muted-foreground">Draft version</dt><dd>{versionLabel}</dd></div>
          ) : null}
        </dl>

        <section aria-labelledby={`${baseId}-entities`}>
          <h3 className="text-sm font-medium" id={`${baseId}-entities`}>Resolved entities</h3>
          <ul className="mt-1 space-y-1 text-sm">
            {proposal.resolved_entities.map((entity) => (
              <li key={`${entity.group}:${entity.record_id}`}>
                {entity.label} · <Identifier>{entity.record_id}</Identifier> · {entity.group}
              </li>
            ))}
          </ul>
        </section>

        <section aria-labelledby={`${baseId}-constraints`} className="space-y-2">
          <h3 className="text-sm font-medium" id={`${baseId}-constraints`}>Constraints and objectives</h3>
          {ended ? (
            // Ended drafts are read-only facts: the server-composed descriptions
            // and nothing to press.
            <ul className="list-disc space-y-1 pl-5 text-sm">
              {proposal.constraints.map((constraint, index) => (
                <li key={`${constraint.kind}-${index}`}>{constraint.description}</li>
              ))}
            </ul>
          ) : (
            <ul className="space-y-3">
              {rows.map((row, index) => {
                const fields = FIELDS[row.input.kind] ?? [];
                const errors = rowErrors[index];
                const isLast = rows.length === 1;
                const removeHintId = `${baseId}-row${index}-remove`;
                return (
                  <li key={`${row.input.kind}:${row.input.record_id}:${row.input.related_record_id ?? ""}:${index}`}>
                    <div aria-label={row.description} className="space-y-2 rounded-lg border p-3" role="group">
                      <p className="text-sm">{row.description}</p>
                      <div className="flex flex-wrap items-start gap-3">
                        {fields.map((field) => {
                          const errorId = `${baseId}-row${index}-${field.key}-error`;
                          const message = errors[field.key];
                          return (
                            <div className="space-y-1 text-sm" key={field.key}>
                              <label className="block" htmlFor={`${baseId}-row${index}-${field.key}`}>{field.label}</label>
                              <Input
                                aria-describedby={message ? errorId : undefined}
                                aria-invalid={message ? true : undefined}
                                aria-label={field.label}
                                className="min-h-11 w-32"
                                disabled={!rowsEditable}
                                id={`${baseId}-row${index}-${field.key}`}
                                onChange={(event) => updateField(index, field.key, event.target.value)}
                                step={field.step}
                                type="number"
                                value={String(row.input[field.key] ?? "")}
                              />
                              {message ? (
                                <p className="text-sm text-destructive" id={errorId}>{message}</p>
                              ) : null}
                            </div>
                          );
                        })}
                        <div className="space-y-1 text-sm">
                          <Button
                            aria-describedby={isLast ? removeHintId : undefined}
                            aria-label={`Remove ${row.description}`}
                            className="min-h-11"
                            disabled={!rowsEditable || isLast}
                            onClick={() => removeRow(index)}
                            type="button"
                            variant="ghost"
                          >Remove</Button>
                          {isLast ? (
                            <p className="text-xs text-muted-foreground" id={removeHintId}>Discard the draft instead</p>
                          ) : null}
                        </div>
                      </div>
                    </div>
                  </li>
                );
              })}
            </ul>
          )}
        </section>

        <section aria-labelledby={`${baseId}-locks`}>
          <h3 className="text-sm font-medium" id={`${baseId}-locks`}>Preserved locks</h3>
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
        {ended ? null : (
          <EditableFooter
            acknowledged={acknowledged}
            agentTurnInFlight={agentTurnInFlight}
            baseId={baseId}
            canSave={canSave}
            changedUnderEdits={changedUnderEdits}
            confirmingDiscard={confirmingDiscard}
            discardRef={discardRef}
            hasDifference={hasDifference}
            inFlightId={inFlightId}
            keepRef={keepRef}
            mutationPending={mutationPending}
            onCancel={resetEdits}
            onConfirmDiscard={() => {
              rejection.mutate(
                { expected_resource_version: proposal.resource_version },
                { onSettled: () => setConfirmingDiscard(false) },
              );
            }}
            onKeep={() => {
              returnFocusToDiscard.current = true;
              setConfirmingDiscard(false);
            }}
            onLoad={resetEdits}
            onRefresh={() => query.refetch()}
            onRun={() => run.mutate({
              proposal_id: proposal.proposal_id,
              expected_resource_version: proposal.resource_version,
            })}
            onSave={save}
            onStartDiscard={() => setConfirmingDiscard(true)}
            proposal={proposal}
            runDescriptionId={runDescriptionId}
            runDisabled={runDisabled}
            runExplanation={runExplanation}
            savedLabel={savedLabel}
            staleDescriptionId={staleDescriptionId}
          />
        )}
      </CardFooter>
    </Card>
  );
}

type EditableFooterProps = Readonly<{
  proposal: Proposal;
  baseId: string;
  acknowledged: { schedule_run_id: string; status: string } | null;
  agentTurnInFlight: boolean;
  canSave: boolean;
  changedUnderEdits: boolean;
  confirmingDiscard: boolean;
  discardRef: RefObject<HTMLButtonElement | null>;
  keepRef: RefObject<HTMLButtonElement | null>;
  hasDifference: boolean;
  inFlightId: string;
  mutationPending: boolean;
  onCancel: () => void;
  onConfirmDiscard: () => void;
  onKeep: () => void;
  onLoad: () => void;
  onRefresh: () => void;
  onRun: () => void;
  onSave: () => void;
  onStartDiscard: () => void;
  runDescriptionId: string;
  runDisabled: boolean;
  runExplanation: string;
  savedLabel: string | null;
  staleDescriptionId: string;
}>;

function EditableFooter(props: EditableFooterProps) {
  const {
    proposal, acknowledged, agentTurnInFlight, canSave, changedUnderEdits, confirmingDiscard,
    discardRef, keepRef, hasDifference, inFlightId, mutationPending, runDescriptionId,
    runDisabled, runExplanation, savedLabel, staleDescriptionId,
  } = props;
  const latest = proposal.version_ordinal != null ? `v${proposal.version_ordinal}` : null;
  const describedBy = (...ids: (string | false | undefined)[]) =>
    ids.filter(Boolean).join(" ") || undefined;
  return (
    <>
      {changedUnderEdits ? (
        <div className="space-y-2 rounded-lg border border-destructive/40 p-3">
          <p aria-live="polite" className="text-sm" role="status">
            {latest ? `This draft changed to ${latest}.` : "This draft changed."} Your edits were not saved.
          </p>
          {/* UX-DR35: each action carries its own treatment. Cancel, Keep, Load and
              Refresh are all outline buttons, so each takes a distinct border colour
              rather than sharing one signature (stateMatrix's merged-treatment rule). */}
          <Button className="min-h-11 border-primary" onClick={props.onLoad} type="button" variant="outline">
            {latest ? `Load ${latest}` : "Load latest"}
          </Button>
        </div>
      ) : null}
      {savedLabel !== null ? (
        <p aria-live="polite" className="text-sm" role="status">{savedLabel}</p>
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
      {agentTurnInFlight ? (
        <p className="text-sm text-muted-foreground" id={inFlightId}>{IN_FLIGHT_HINT}</p>
      ) : null}

      {/* Edits: Cancel and Save act on the local list. Stale keeps Save mounted
          and disabled, carrying the explanation, rather than a decoy. */}
      <div className="flex flex-wrap gap-2">
        <Button
          className="min-h-11"
          disabled={!hasDifference}
          onClick={props.onCancel}
          type="button"
          variant="outline"
        >Cancel</Button>
        <Button
          aria-describedby={describedBy(proposal.stale && staleDescriptionId, agentTurnInFlight && inFlightId)}
          className="min-h-11"
          disabled={!canSave}
          onClick={props.onSave}
          type="button"
        >Save changes</Button>
      </div>
      <Separator />
      <div className="space-y-2">
        <p className="text-sm text-muted-foreground" id={runDescriptionId}>
          {runExplanation}
        </p>
        <div className="flex flex-wrap items-start justify-between gap-2">
          <Button
            aria-describedby={describedBy(runDescriptionId, agentTurnInFlight && inFlightId)}
            className="min-h-11"
            disabled={runDisabled}
            onClick={props.onRun}
            type="button"
            variant="secondary"
          >Run optimization</Button>
          {confirmingDiscard ? (
            <div aria-label="Confirm discard" className="space-y-2 rounded-lg border border-destructive/40 p-3" role="group">
              <p className="text-sm">Discard this draft? It can&apos;t be restored.</p>
              <div className="flex gap-2">
                <Button
                  aria-describedby={describedBy(agentTurnInFlight && inFlightId)}
                  className="min-h-11"
                  disabled={mutationPending || agentTurnInFlight}
                  onClick={props.onConfirmDiscard}
                  type="button"
                  variant="destructive"
                >Discard</Button>
                <Button
                  className="min-h-11 border-foreground"
                  onClick={props.onKeep}
                  ref={keepRef}
                  type="button"
                  variant="outline"
                >Keep</Button>
              </div>
            </div>
          ) : (
            // Available while stale, deliberately: it changes no baseline and is
            // the only terminal path a stale draft has.
            <Button
              aria-describedby={describedBy(agentTurnInFlight && inFlightId)}
              className="min-h-11"
              disabled={mutationPending || agentTurnInFlight}
              onClick={props.onStartDiscard}
              ref={discardRef}
              type="button"
              variant="destructive"
            >Discard draft</Button>
          )}
        </div>
      </div>
      {proposal.stale ? (
        <div>
          <Button className="min-h-11 border-muted-foreground" onClick={props.onRefresh} type="button" variant="outline">Refresh proposal</Button>
        </div>
      ) : null}
    </>
  );
}
