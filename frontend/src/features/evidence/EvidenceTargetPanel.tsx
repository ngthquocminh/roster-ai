import { useEffect, useRef } from "react";
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
import type { EvidenceTarget } from "./locator";
import { rememberOrigin, type EvidenceOrigin } from "./origin";
import { markEvidenceUnavailable } from "./availability";

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

function RecordFields({ record }: Readonly<{ record: Record<string, unknown> }>) {
  const entries = Object.entries(record).filter(([key]) => key !== "end_minute");
  return (
    <dl className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {entries.map(([key, value]) => {
        const isWindow = key === "start_minute" && typeof value === "number" && typeof record.end_minute === "number";
        const isIdentifier = key.endsWith("_id") && typeof value === "string";
        return (
          <div className="min-w-0" key={key}>
            <dt className="text-xs text-muted-foreground">{isWindow ? "Window" : fieldLabel(key)}</dt>
            <dd className="mt-1 break-words text-sm">
              {isWindow ? formatMinuteWindow(value, record.end_minute as number) : isIdentifier ? (
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
  const highlightRef = useRef<HTMLDivElement>(null);
  const focusedTarget = useRef<string | null>(null);
  const targetKey = `${scenarioId}:${target.group}:${target.record}:${target.version}`;
  const errorCode = getErrorCode(query.error);
  const detail = targetDetail(target);
  const accessibleName = `Evidence target: ${target.group} ${target.record}${detail ? `, ${detail}` : ""}, fixture ${target.version}`;

  useEffect(() => {
    if (!query.isSuccess || !query.data || focusedTarget.current === targetKey) return;
    focusedTarget.current = targetKey;
    highlightRef.current?.focus();
  }, [query.data, query.isSuccess, targetKey]);

  useEffect(() => {
    if (origin && errorCode === "evidence_not_found") markEvidenceUnavailable(origin);
  }, [errorCode, origin]);

  const returnControl = origin ? (
    <Button
      className="min-h-11"
      onClick={() => {
        rememberOrigin(origin);
        navigate(`/scenarios/${scenarioId}?conversation=${encodeURIComponent(origin.conversationId)}`);
      }}
      type="button"
      variant="outline"
    >
      Return to claim
    </Button>
  ) : null;

  if (query.isPending) {
    return (
      <div aria-label="Loading cited evidence" className="mt-4 space-y-3 rounded-evidence border p-evidence-inset" role="status">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-16 w-full" />
      </div>
    );
  }

  if (query.isError && query.data) {
    return (
      <InlineAlert
        action={<Button className="min-h-11" onClick={() => { void query.refetch(); }} type="button" variant="outline">Refresh</Button>}
        className="mt-4"
        description={`Stale — last verified at ${formatTimestamp(new Date(query.dataUpdatedAt).toISOString())}`}
        descriptionRole="status"
        title="Stale evidence"
      />
    );
  }

  if (query.isError && errorCode === "evidence_version_mismatch") {
    return (
      <InlineAlert
        action={returnControl}
        className="mt-4"
        description={`The cited version ${target.version} does not match the selected version ${selectedVersion ?? "unknown"}. No current or similar record was substituted.`}
        title="Version mismatch"
        variant="destructive"
      />
    );
  }

  if (query.isError && errorCode === "evidence_not_found") {
    return (
      <InlineAlert
        action={<div className="flex flex-wrap gap-3"><Button className="min-h-11" onClick={() => { void query.refetch(); }} type="button" variant="outline">Retry</Button>{returnControl}</div>}
        className="mt-4"
        description={`The locator ${target.group} ${target.record}${detail ? `, ${detail}` : ""} could not resolve in the exact cited version ${target.version}. No current or similar record was substituted.`}
        title="Missing evidence"
        variant="destructive"
      />
    );
  }

  if (query.isError && (errorCode === "resource_not_found" || errorCode === "request_forbidden")) {
    return (
      <InlineAlert
        action={returnControl}
        className="mt-4"
        description="Evidence is not available to this session."
        title="Unauthorized"
        variant="destructive"
      />
    );
  }

  if (!query.data) return null;

  return (
    <div className="mt-4">
    <EvidenceHighlight aria-label={accessibleName} ref={highlightRef} role="region">
      <p className="text-xs font-medium uppercase tracking-wide">Cited evidence</p>
      <div className="mt-2 flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="font-semibold">{target.group}</h3>
          <dl className="mt-2 grid gap-x-6 gap-y-2 sm:grid-cols-2">
            <div><dt className="text-xs text-muted-foreground">Targeted field</dt><dd className="text-sm">{detail ?? "Whole record"}</dd></div>
            <div><dt className="text-xs text-muted-foreground">Cited version</dt><dd className="break-all font-mono text-xs">{target.version}</dd></div>
          </dl>
        </div>
        {returnControl}
      </div>
      <RecordFields record={query.data as Record<string, unknown>} />
    </EvidenceHighlight>
    </div>
  );
}
