import { ChevronDown } from "lucide-react";
import { useNavigate } from "react-router";

import type { ProvenanceItem, RunProvenance } from "@/api/provenance";
import { EvidenceLink } from "@/components/primitives/EvidenceLink";
import { IdentifierCopyButton } from "@/components/primitives/IdentifierCopyButton";
import { Button } from "@/components/ui/button";
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible";
import { toSearchParams } from "@/features/evidence/locator";
import { originElementId, rememberOrigin, type EvidenceOrigin } from "@/features/evidence/origin";
import { formatTimestamp } from "@/lib/formatTimestamp";

const IDENTIFIERS = [
  ["site_id", "site identifier"],
  ["actor_id", "actor identifier"],
  ["initiated_by_actor_id", "initiating actor identifier"],
  ["decided_by_actor_id", "deciding actor identifier"],
  ["schedule_run_id", "schedule run identifier"],
  ["schedule_version_id", "schedule version identifier"],
  ["approval_id", "approval identifier"],
  ["audit_id", "audit identifier"],
  ["conversation_id", "conversation identifier"],
  ["agent_run_id", "agent run identifier"],
  ["tool_call_id", "tool call identifier"],
  ["request_id", "request identifier"],
  ["attempt_id", "attempt identifier"],
  ["job_attempt_id", "job attempt identifier"],
  ["scenario_version_id", "scenario version identifier"],
] as const;

function itemLabel(item: ProvenanceItem): string {
  switch (item.item_type) {
    case "solver_run": return `Solver run: ${item.status}`;
    case "run_progress": return `Run progress: ${item.status}`;
    case "draft": return "Draft proposed";
    case "evidence_claim": return `Evidence claim: ${item.claim}`;
    case "tool_proposal": return `Tool proposed: ${item.tool_name}`;
    case "approval_request": return `Approval requested: ${item.state}`;
    case "approval_decision": return `Approval decision: ${item.outcome}`;
    case "audit_record": return `Audit: ${item.action} — ${item.outcome}`;
    case "baseline_promotion": return "Baseline promoted";
  }
}

function fieldOrRange(ref: ProvenanceItem["evidence_refs"][number]): string | undefined {
  const range = ref.start_minute != null && ref.end_minute != null
    ? `${ref.start_minute}–${ref.end_minute} minutes`
    : undefined;
  if (ref.field && range) return `${ref.field}, ${range}`;
  return ref.field ?? range;
}

function SafeDetails({ item }: Readonly<{ item: ProvenanceItem }>) {
  const rows: [string, string][] = [];
  if (item.item_type === "solver_run") {
    rows.push(["Comparison", item.comparison_status]);
    if (item.comparison_reason) rows.push(["Comparison reason", item.comparison_reason]);
    if (item.reason) rows.push(["Reason", item.reason]);
  }
  if (item.item_type === "run_progress" && item.reason) rows.push(["Reason", item.reason]);
  if (item.item_type === "draft") rows.push(["Consequence", item.consequence_summary]);
  if (item.item_type === "evidence_claim") rows.push(["Persisted value", `${String(item.value)}${item.unit ? ` ${item.unit}` : ""}`]);
  if (item.item_type === "approval_request") {
    rows.push(["Consequence", item.consequence_summary], ["Parameter hash", item.parameter_hash], ["Consequence hash", item.consequence_hash], ["Policy", item.policy_version]);
  }
  if (item.item_type === "audit_record") {
    rows.push(["Summary", item.safe_summary], ["Parameter hash", item.parameter_hash], ["Consequence hash", item.consequence_hash], ["Policy", item.policy_version], ["Application", item.app_version]);
    if (item.worker_facts.lease_owner) rows.push(["Worker lease owner", item.worker_facts.lease_owner]);
    if (item.worker_facts.attempt_id) rows.push(["Worker attempt", item.worker_facts.attempt_id]);
    if (item.worker_facts.fencing_epoch != null) rows.push(["Worker fencing epoch", String(item.worker_facts.fencing_epoch)]);
  }
  if (!rows.length) return null;
  return (
    <Collapsible className="mt-2">
      <CollapsibleTrigger asChild>
        <Button className="min-h-11" type="button" variant="ghost">
          Details <ChevronDown aria-hidden="true" className="size-4" />
        </Button>
      </CollapsibleTrigger>
      <CollapsibleContent>
        <dl className="grid gap-1 rounded-md bg-muted/40 p-3 text-sm">
          {rows.map(([label, value]) => <div className="grid gap-1 sm:grid-cols-[10rem_1fr]" key={label}><dt className="font-medium">{label}</dt><dd className="min-w-0 break-words">{value}</dd></div>)}
        </dl>
      </CollapsibleContent>
    </Collapsible>
  );
}

export function ProvenanceTimeline({ provenance, scenarioId }: Readonly<{ provenance: RunProvenance; scenarioId: string }>) {
  const navigate = useNavigate();
  return (
    <ol aria-label="Decision provenance" className="space-y-3">
      {provenance.items.map((item, itemIndex) => (
        <li className="min-w-0 rounded-xl border p-4" key={`${item.item_type}:${item.occurred_at}:${itemIndex}`}>
          <div className="flex flex-wrap items-start justify-between gap-2">
            <p className="font-medium">{itemLabel(item)}</p>
            <time className="text-sm text-muted-foreground" dateTime={item.occurred_at}>{formatTimestamp(item.occurred_at)}</time>
          </div>
          <div aria-label="Identifiers" className="mt-2 flex min-w-0 flex-wrap gap-x-4 gap-y-1" role="group">
            {IDENTIFIERS.map(([field, label]) => item[field] ? <IdentifierCopyButton identifierType={label} key={field} value={item[field]} /> : null)}
            {item.item_type === "draft" ? <><IdentifierCopyButton identifierType="proposal identifier" value={item.proposal_id} /><IdentifierCopyButton identifierType="proposal version identifier" value={item.proposal_version_id} /></> : null}
          </div>
          {item.item_type === "baseline_promotion" ? (
            <div className="mt-2 flex min-w-0 flex-wrap items-center gap-3 text-sm">
              <span>Before</span>{item.before_version ? <IdentifierCopyButton identifierType="previous baseline version" value={item.before_version} /> : <span>None</span>}
              <span>After</span><IdentifierCopyButton identifierType="promoted baseline version" value={item.after_version} />
            </div>
          ) : null}
          {item.evidence_refs.length ? <ul aria-label="Evidence references" className="mt-2 flex flex-wrap gap-2">{item.evidence_refs.map((ref, refIndex) => {
            const origin: EvidenceOrigin = { conversationId: item.conversation_id ?? provenance.schedule_run_id, activityId: `${item.item_type}-${itemIndex}`, segmentIndex: itemIndex, refIndex };
            return <li key={`${ref.group}:${ref.record_id}:${refIndex}`}><EvidenceLink fieldOrRange={fieldOrRange(ref)} group={ref.group} id={originElementId(origin)} onActivate={() => { rememberOrigin(origin); navigate(`/scenarios/${scenarioId}/data?${toSearchParams(ref)}`, { state: { evidenceOrigin: origin } }); }} record={ref.record_id} version={ref.scenario_version_id} /></li>;
          })}</ul> : null}
          <SafeDetails item={item} />
        </li>
      ))}
    </ol>
  );
}
