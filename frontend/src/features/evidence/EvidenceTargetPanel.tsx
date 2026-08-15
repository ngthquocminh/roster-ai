import { useEffect, useRef, type ReactNode } from "react";
import { useNavigate } from "react-router";

import { EvidenceHighlight } from "@/components/primitives/EvidenceHighlight";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useEvidenceRecord } from "@/hooks/useEvidenceRecord";
import { formatMinuteWindow } from "@/lib/formatShiftWindow";
import { getErrorCode } from "@/lib/errors";
import { formatTimestamp } from "@/lib/formatTimestamp";
import { EVIDENCE_GROUP_LABEL, type EvidenceTarget } from "./locator";
import { rememberOrigin, type EvidenceOrigin } from "./origin";
import { markEvidenceUnavailable, unmarkEvidenceUnavailable } from "./availability";

function fieldLabel(key: string): string {
  return key.split("_").map((part, index) => {
    if (part === "id") return "ID";
    return index === 0 ? part.replace(/^./, (letter) => letter.toUpperCase()) : part;
  }).join(" ");
}

function displayValue(value: unknown): string {
  if (value == null || value === "") return "—";
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => displayValue(item)).join(", ") : "—";
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, nested]) => `${fieldLabel(key)}: ${displayValue(nested)}`)
      .join("; ");
  }
  return String(value);
}

function targetDetail(target: EvidenceTarget): string | undefined {
  const range = target.start !== undefined && target.end !== undefined
    ? `${target.start}–${target.end} minutes`
    : undefined;
  if (target.field && range) return `${target.field}, ${range}`;
  return target.field ?? range;
}

function RecordFields({ record }: Readonly<{ record: object }>) {
  const entries = Object.entries(record);
  const start = entries.find(([key]) => key === "start_minute")?.[1];
  const end = entries.find(([key]) => key === "end_minute")?.[1];
  // Only collapse the pair into one "Window" row when BOTH ends are numbers.
  // Filtering `end_minute` unconditionally used to delete a present boundary
  // value whenever `start_minute` was null — a silent omission on the one
  // surface whose contract is "show the exact cited record, substitute nothing".
  const hasWindow = typeof start === "number" && typeof end === "number";
  return (
    <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries
        .filter(([key]) => !(hasWindow && key === "end_minute"))
        .map(([key, value]) => {
          const isWindow = hasWindow && key === "start_minute";
          const isIdentifier = key.endsWith("_id") && typeof value === "string";
          return (
            <div className="min-w-0" key={key}>
              <dt className="text-xs text-muted-foreground">{isWindow ? "Window" : fieldLabel(key)}</dt>
              <dd className="mt-1 break-words text-sm">
                {isWindow ? formatMinuteWindow(start as number, end as number) : isIdentifier ? (
                  <IdentifierCopyButton identifierType={fieldLabel(key)} value={value} />
                ) : displayValue(value)}
              </dd>
            </div>
          );
        })}
    </dl>
  );
}

export function EvidenceTargetPanel({
  origin,
  scenarioId,
  selectedVersion,
  target,
}: Readonly<{
  origin?: EvidenceOrigin;
  scenarioId: string;
  selectedVersion?: string;
  target: EvidenceTarget;
}>) {
  const navigate = useNavigate();
  const query = useEvidenceRecord(scenarioId, target);
  const regionRef = useRef<HTMLDivElement>(null);
  const focusedState = useRef<string | null>(null);
  const errorCode = getErrorCode(query.error);
  const detail = targetDetail(target);
  const groupLabel = EVIDENCE_GROUP_LABEL[target.group];
  const accessibleName = `Evidence target: ${groupLabel} ${target.record}${detail ? `, ${detail}` : ""}, cited version ${target.version}`;

  // The key carries every part of the locator the region ANNOUNCES. Keying on
  // group/record/version alone meant a re-target that only changed the field or
  // window updated the accessible name without moving focus, so the announced
  // target and the focused target diverged.
  const targetKey = `${scenarioId}:${target.group}:${target.record}:${target.version}:${target.field ?? ""}:${target.start ?? ""}:${target.end ?? ""}`;
  const settledState = query.isPending
    ? null
    : query.isError && !query.data
      ? `error:${errorCode ?? "unclassified"}`
      : query.isError
        ? "stale"
        : "record";
  const focusKey = settledState ? `${targetKey}|${settledState}` : null;

  // EXPERIENCE.md:137 — focus lands AFTER the row/window loads, never on an
  // empty box. ScenarioWorkspace.tsx:26-30 documents why a second effect firing
  // here interrupts a screen reader mid-announcement. The region ref is shared
  // by the record and by every terminal exception state, so when an error
  // replaces the highlight the focus follows the replacement instead of
  // collapsing to <body>.
  useEffect(() => {
    if (!focusKey || focusedState.current === focusKey) return;
    const node = regionRef.current;
    if (!node) return;
    focusedState.current = focusKey;
    node.focus();
  }, [focusKey]);

  // Derived at render time and never written back (Decision 6). The mark is
  // reversible so a Retry that resolves does not leave the timeline asserting
  // the opposite of this panel.
  useEffect(() => {
    if (!origin) return;
    if (query.isError && errorCode === "evidence_not_found") markEvidenceUnavailable(origin);
    else if (query.isSuccess) unmarkEvidenceUnavailable(origin);
  }, [errorCode, origin, query.isError, query.isSuccess]);

  const returnControl = origin ? (
    <Button
      className="min-h-11"
      onClick={() => {
        // Written to storage AND passed as history state: the Chat entry the
        // planner lands on may predate the jump, and storage can be disabled.
        rememberOrigin(origin);
        navigate(`/scenarios/${scenarioId}?conversation=${encodeURIComponent(origin.conversationId)}`, {
          state: { evidenceOrigin: origin },
        });
      }}
      type="button"
      variant="outline"
    >
      Return to claim
    </Button>
  ) : null;

  const retryControl = (
    <Button className="min-h-11" onClick={() => { void query.refetch(); }} type="button" variant="outline">
      Retry
    </Button>
  );

  if (query.isPending) {
    return (
      <div aria-label="Loading cited evidence" className="mt-4 space-y-3 rounded-evidence border p-evidence-inset" role="status">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  // Decision 5: branch on the RFC 7807 code, never the transport status — and
  // branch on it BEFORE the stale check. A cached record plus a coded failure
  // used to render "Stale — Refresh" (an action that can never succeed) while
  // the timeline simultaneously marked the same claim "Evidence unavailable".
  if (query.isError && errorCode === "evidence_version_mismatch") {
    return (
      <div className="mt-4 outline-none" ref={regionRef} tabIndex={-1}>
        <InlineAlert
          action={returnControl}
          description={`The cited version ${target.version} does not match the selected version ${selectedVersion ?? "unknown"}. No current or similar record was substituted.`}
          title="Version mismatch"
          variant="destructive"
        />
      </div>
    );
  }

  if (query.isError && errorCode === "evidence_not_found") {
    return (
      <div className="mt-4 outline-none" ref={regionRef} tabIndex={-1}>
        <InlineAlert
          action={<div className="flex flex-wrap gap-3">{retryControl}{returnControl}</div>}
          description={`The locator ${groupLabel} ${target.record}${detail ? `, ${detail}` : ""} could not resolve in the exact cited version ${target.version}. No current or similar record was substituted.`}
          title="Missing evidence"
          variant="destructive"
        />
      </div>
    );
  }

  // Copy is byte-identical whether the record exists or not: it states no value
  // and makes no claim about existence (AC2's non-disclosure clause).
  if (query.isError && (errorCode === "resource_not_found" || errorCode === "request_forbidden")) {
    return (
      <div className="mt-4 outline-none" ref={regionRef} tabIndex={-1}>
        <InlineAlert
          action={returnControl}
          description="Evidence is not available to this session."
          title="Unauthorized"
          variant="destructive"
        />
      </div>
    );
  }

  const record = query.data;

  // Stale: an uncoded failure (transport, 5xx) arrived while a previously
  // resolved record is still cached. ScenarioWorkspace.tsx:118-137 is the
  // approved pattern — the message is the only live region, the control sits
  // outside it, and THE RECORD KEEPS RENDERING. Replacing it with a banner
  // discarded evidence the planner already had.
  const staleBanner = query.isError && record ? (
    <div className="mb-3 flex flex-wrap items-center justify-between gap-3 rounded-lg border border-destructive/40 px-3 py-2">
      <span className="text-sm" role="status">
        Stale — last verified at {formatTimestamp(new Date(query.dataUpdatedAt).toISOString())}
      </span>
      {/* Retry only: the record below is still rendered and carries its own
          Return to claim, so repeating it here would duplicate the control. */}
      {retryControl}
    </div>
  ) : null;

  // Every remaining failure is terminal (`retry: false`), so it must still say
  // something. Returning null left the planner on a force-switched tab with no
  // panel, no message and no way back — indistinguishable from a broken link.
  if (query.isError && !record) {
    return (
      <div className="mt-4 outline-none" ref={regionRef} tabIndex={-1}>
        <InlineAlert
          action={<div className="flex flex-wrap gap-3">{retryControl}{returnControl}</div>}
          description={`The cited evidence could not be loaded${errorCode ? ` (${errorCode})` : ""}. No current or similar record was substituted.`}
          title="Evidence unavailable"
          variant="destructive"
        />
      </div>
    );
  }

  if (!record) return null;

  const highlight: ReactNode = (
    <EvidenceHighlight aria-label={accessibleName} ref={regionRef} role="region">
      <p className="text-xs font-medium uppercase tracking-wide">Cited evidence</p>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{groupLabel}</h3>
          <dl className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            <div><dt className="text-xs text-muted-foreground">Targeted field</dt><dd className="text-sm">{detail ?? "Whole record"}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Cited version</dt><dd className="break-all font-mono text-xs">{target.version}</dd></div>
          </dl>
        </div>
        {returnControl}
      </div>
      <RecordFields record={record} />
    </EvidenceHighlight>
  );

  return (
    <div className="mt-4">
      {staleBanner}
      {highlight}
    </div>
  );
}
