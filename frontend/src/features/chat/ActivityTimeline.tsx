import { useId } from "react";

import type { Timeline } from "@/api/conversations";
import { EmptyState } from "@/components/primitives/EmptyState";
import { EvidenceLink } from "@/components/primitives/EvidenceLink";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { StatusBadge } from "@/components/primitives/StatusBadge";
import { DraftCard } from "./DraftCard";
import { ApprovalRequestCard } from "@/features/approvals/ApprovalRequestCard";
import { toSearchParams } from "@/features/evidence/locator";
import { isEvidenceUnavailable, useEvidenceAvailability } from "@/features/evidence/availability";
import {
  originElementId,
  rememberOrigin,
  type EvidenceOrigin,
} from "@/features/evidence/origin";
import type { NavigateFunction } from "react-router";

type Activity = Timeline["items"][number];
type AgentResponse = Extract<Activity, { activity_type: "agent_response" }>;
type Clarification = Extract<Activity, { activity_type: "clarification" }>;
type TerminalOutcome = Extract<Activity, { activity_type: "terminal_outcome" }>;
type Claim = Extract<AgentResponse["response"]["segments"][number], { kind: "claim" }>;

// UX-DR8 asks the link to name the exact field AND range. Returning the field
// first meant the range branch was unreachable in production: every locator the
// calculators emit sets `field` alongside `start_minute`/`end_minute`, so only
// the test fixture (which leaves `field` null) ever reached it.
function fieldOrRange(reference: Claim["evidence_refs"][number]): string | undefined {
  const range =
    reference.start_minute != null && reference.end_minute != null
      ? `${reference.start_minute}–${reference.end_minute} minutes`
      : undefined;
  if (reference.field && range) return `${reference.field}, ${range}`;
  return reference.field ?? range;
}

// A claim renders no prose of its own and the gate forbids numerals in prose,
// so without this the answer cannot say WHICH task or window a number belongs
// to — the number would be exact and unattributed at the same time.
function claimSubject(claim: Claim): string | undefined {
  const parts: string[] = [];
  if (claim.arguments.task_id) parts.push(claim.arguments.task_id);
  if (claim.arguments.family) parts.push(claim.arguments.family);
  if (claim.arguments.start_minute != null && claim.arguments.end_minute != null) {
    parts.push(`${claim.arguments.start_minute}–${claim.arguments.end_minute} min`);
  }
  return parts.length ? parts.join(" · ") : undefined;
}

// Exactness is this feature's whole premise, so neither a raw float repr
// (90.00000000000001) nor a fixed 2-decimal truncation is acceptable: the first
// is noise, the second renders a real 0.0001 as "0.00" beside an Evidence link
// that proves it is not zero. `toPrecision(12)` drops IEEE-754 representation
// noise well below any magnitude the projection carries, and `Number()` strips
// the trailing zeros it introduces.
function formatClaimValue(value: number): string {
  if (Number.isInteger(value)) return String(value);
  return String(Number(value.toPrecision(12)));
}

function ClaimSegment({
  claim,
  item,
  navigate,
  segmentIndex,
}: Readonly<{
  claim: Claim;
  item: AgentResponse;
  navigate: NavigateFunction;
  segmentIndex: number;
}>) {
  if (claim.verdict === "failed") {
    return (
      <span className="text-destructive" data-claim-state="failed">
        Claim unavailable: {claim.failure?.replaceAll("_", " ") ?? "calculation failed"}
      </span>
    );
  }
  const subject = claimSubject(claim);
  // A proven-empty match set is supported and carries NO locator, because
  // EvidenceRefV1 addresses records and absence has none. Rendering it as a bare
  // "0" left a number with no adjacent Evidence link, which AC2 forbids -- so it
  // gets an explicit state instead of an implicit absence.
  if (!claim.evidence_refs.length) {
    return (
      <span className="text-muted-foreground" data-claim-state="empty">
        No matching records{subject ? ` (${subject})` : ""}
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-claim-state="supported">
      {/* Exactness is this feature's whole premise, so a raw float repr
          (90.00000000000001) is not acceptable output. Volume demand carries
          float amounts throughout the fixture, so this is reachable, not
          theoretical. Integers keep rendering unchanged. */}
      <span>
        {formatClaimValue(Number(claim.value))} {claim.unit}
        {subject ? <span className="text-muted-foreground"> ({subject})</span> : null}
      </span>
      {claim.evidence_refs.map((reference, refIndex) => {
        const origin: EvidenceOrigin = {
          conversationId: item.conversation_id,
          activityId: item.activity_id,
          segmentIndex,
          refIndex,
        };
        const activate = () => {
          rememberOrigin(origin);
          navigate(
            `/scenarios/${item.scenario_id}/data?${toSearchParams(reference)}`,
            { state: { evidenceOrigin: origin } },
          );
        };
        // Keyed by ref POSITION, not by locator content: two refs can cite the
        // same group/record/field for different windows, and a colliding key
        // made React reconcile the very elements focus restoration targets.
        return (
          <span className="inline-flex flex-wrap items-center gap-2" key={`ref-${refIndex}`}>
          <EvidenceLink
            fieldOrRange={fieldOrRange(reference)}
            group={reference.group}
            id={originElementId(origin)}
            onActivate={activate}
            record={reference.record_id}
            version={reference.scenario_version_id}
          />
          {isEvidenceUnavailable(origin) ? <span className="text-destructive">Evidence unavailable</span> : null}
          </span>
        );
      })}
    </span>
  );
}

function AgentResponse({ item, navigate }: Readonly<{ item: AgentResponse; navigate: NavigateFunction }>) {
  // An empty segment list means no visible answer was saved. It does NOT mean
  // the run failed: `terminal_status` returns `agent_completed` whenever a
  // grounded response exists, so a model that answers with zero segments
  // completes successfully and lands here too. The activity payload carries no
  // run status, so this cannot tell the two apart -- and asserting "did not
  // complete" in destructive styling was therefore wrong for the completed case.
  // Stay neutral and factual. New failures persist as terminal_outcome; this
  // branch remains only for historical agent_response rows with no segments.
  if (!item.response.segments.length) {
    return (
      <div aria-label="ShiftMind response" className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">ShiftMind</p>
        <p className="text-sm text-muted-foreground" data-response-state="empty">
          No answer was saved for this turn.
        </p>
      </div>
    );
  }
  return (
    <div aria-label="ShiftMind response" className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">ShiftMind</p>
      <p className="flex flex-wrap items-center gap-2 text-sm whitespace-pre-wrap">
        {item.response.segments.map((segment, index) =>
          segment.kind === "prose" ? (
            <span key={`prose-${index}`}>{segment.text}</span>
          ) : (
            <ClaimSegment claim={segment} item={item} key={`claim-${segment.result_id}-${index}`} navigate={navigate} segmentIndex={index} />
          ),
        )}
      </p>
    </div>
  );
}

function Clarification({ item }: Readonly<{ item: Clarification }>) {
  const dropped = item.clarification.dropped_candidate_count;
  const recordsHeadingId = useId();
  return (
    <section aria-label="Clarification" className="space-y-2">
      <StatusBadge status="Clarification" />
      {/* The question is the assistant's own wording and is deliberately NOT
          grounded — clarification is exempt from `_reject_numeric_prose`, so it
          may name entities or numbers the application never verified. Every row
          under the heading below IS application-resolved against the governed
          projection (Decision 5: the model proposes `(group, record_id)` and can
          never supply a label). Naming the list is what lets a planner tell the
          two apart; the resolved `label` carries the record's real name, so a
          fabricated name in the question has something to be checked against. */}
      <p className="text-sm whitespace-pre-wrap">{item.clarification.question}</p>
      {item.clarification.candidates.length ? (
        <>
          <p className="text-xs font-medium text-muted-foreground" id={recordsHeadingId}>
            Records in Scenario Data
          </p>
          <ul
            aria-labelledby={recordsHeadingId}
            className="list-disc space-y-1 pl-5 text-sm"
          >
            {item.clarification.candidates.map((candidate) => (
              <li key={`${candidate.group}:${candidate.record_id}`}>
                {candidate.label} · {candidate.group} · {candidate.record_id}
              </li>
            ))}
          </ul>
        </>
      ) : null}
      {dropped > 0 ? (
        <p className="text-sm text-muted-foreground">
          {dropped} {dropped === 1 ? "candidate" : "candidates"} could not be resolved.
        </p>
      ) : null}
    </section>
  );
}

const TERMINAL_LABELS: Record<string, string> = {
  provider_error: "Provider failure",
  invalid_output: "Invalid output",
  budget_exhausted: "Budget exhausted",
  deadline_exceeded: "Timed out",
  capability_error: "Capability failure",
  refused: "Refusal",
  approval_unsupported: "Approval required",
};

/** The model's own closed-vocabulary refusal cause. Rendering it keeps three
 * genuinely different answers from collapsing into one "Refusal" label, which
 * is the outcome-collapsing EXPERIENCE.md's Voice and Tone table forbids. Safe
 * because the vocabulary is closed: the model selects, these strings are ours. */
const REFUSAL_LABELS: Record<string, string> = {
  unsupported_request: "Not supported",
  capability_unavailable: "Capability unavailable",
  out_of_scope: "Out of scope",
};

function terminalLabel(item: TerminalOutcome["outcome"]): string {
  if (item.reason === "refused" && item.refusal_reason) {
    return REFUSAL_LABELS[item.refusal_reason] ?? "Refusal";
  }
  // Falls back rather than returning undefined. An unmapped reason previously
  // left `aria-label={undefined}`, so the live region lost its accessible name
  // and the alert rendered an empty title — the failure mode of an older bundle
  // meeting a newer backend.
  return TERMINAL_LABELS[item.reason] ?? "Turn ended";
}

function TerminalOutcome({
  item,
  isLatest,
}: Readonly<{ item: TerminalOutcome; isLatest: boolean }>) {
  const label = terminalLabel(item.outcome);
  return (
    <div className="space-y-2">
      {/* `role="status"` announces on mount, so making EVERY historical terminal
          outcome a live region replayed the whole failure history to a screen
          reader on load and on every refetch. Only the newest one announces;
          the rest keep the same accessible name as plain content. The next step
          stays outside the region (ScenarioWorkspace's pattern). */}
      <div aria-label={label} role={isLatest ? "status" : undefined}>
        <InlineAlert
          description={`${label}: ${item.outcome.detail}`}
          title={label}
          variant={item.outcome.reason === "refused" ? "default" : "destructive"}
        />
      </div>
      {item.outcome.next_step ? (
        <p className="text-sm text-muted-foreground">{item.outcome.next_step}</p>
      ) : null}
    </div>
  );
}

function ActivityContent({
  item,
  navigate,
  isLatest = false,
}: Readonly<{ item: Activity; navigate: NavigateFunction; isLatest?: boolean }>) {
  switch (item.activity_type) {
    case "planner_message":
      return (
        <div aria-label="Planner message">
          <p className="text-xs font-medium text-muted-foreground">You</p>
          <p className="text-sm whitespace-pre-wrap">{item.text}</p>
        </div>
      );
    case "agent_response":
      return <AgentResponse item={item} navigate={navigate} />;
    case "clarification":
      return <Clarification item={item} />;
    case "draft":
      // No cast: narrowing the discriminated union is exactly what the
      // `const exhaustive: never` guard below exists to keep honest, and
      // `as Draft` disabled that check for this branch alone.
      return (
        <DraftCard
          consequenceSummary={item.consequence_summary}
          proposalId={item.proposal_id}
        />
      );
    case "approval_request":
      return <ApprovalRequestCard approval={{
        approval_id: item.approval_id,
        state: item.approval_state,
        schedule_run_id: item.schedule_run_id,
        candidate_schedule_version_id: item.candidate_schedule_version_id,
        baseline_schedule_version: item.baseline_schedule_version,
        consequence_summary: item.consequence_summary,
        policy_version: item.policy_version,
        expires_at: item.expires_at,
      }} />;
    case "terminal_outcome":
      return <TerminalOutcome isLatest={isLatest} item={item} />;
    default: {
      // `tsc` still proves exhaustiveness at build time via this assignment.
      // At RUNTIME the previous form returned the activity object itself as a
      // React child, which throws and unmounts the entire timeline — so an
      // older bundle meeting a newer backend lost every message rather than one
      // row. AD-20 reserves eight discriminants; four are not implemented yet.
      const exhaustive: never = item;
      void exhaustive;
      return (
        <p className="text-sm text-muted-foreground">
          This entry needs a newer version of the app to display. Reload to
          update.
        </p>
      );
    }
  }
}

// `navigate` is REQUIRED: activation writes the origin to storage before it
// navigates, so an omitted navigate left a live origin behind that the next
// ChatView mount would consume and use to move focus after nothing happened.
export function ActivityTimeline({ items, navigate }: Readonly<{ items: Timeline["items"]; navigate: NavigateFunction }>) {
  // The "Evidence unavailable" marker lives in an external mutable store; this
  // subscribes ONCE per timeline (never inside the segment/ref loops, so the
  // hook count cannot vary) and re-renders when any mark changes.
  useEvidenceAvailability();
  // Deduplicate by activity identity, not array position (UX-DR6): a refetch
  // that re-delivers an already-rendered activity must not produce a second
  // card, and a reorder must not merge two distinct ones.
  const unique = [...new Map(items.map((item) => [item.activity_id, item])).values()];
  if (!unique.length) {
    return (
      <EmptyState explanation="Start a new conversation about this scenario—for example, ask about coverage, demand, or constraints." />
    );
  }
  return (
    <ol aria-label="Conversation activity" className="space-y-3">
      {unique.map((item, index) => (
        <li
          className="rounded-lg border bg-card p-3"
          data-activity-id={item.activity_id}
          key={item.activity_id}
        >
          <ActivityContent
            isLatest={index === unique.length - 1}
            item={item}
            navigate={navigate}
          />
        </li>
      ))}
    </ol>
  );
}
