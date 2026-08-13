import type { Timeline } from "@/api/conversations";
import { EmptyState } from "@/components/primitives/EmptyState";
import { EvidenceLink } from "@/components/primitives/EvidenceLink";

type Activity = Timeline["items"][number];
type AgentResponse = Extract<Activity, { activity_type: "agent_response" }>;
type Claim = Extract<AgentResponse["response"]["segments"][number], { kind: "claim" }>;

function fieldOrRange(reference: Claim["evidence_refs"][number]): string | undefined {
  if (reference.field) return reference.field;
  if (reference.start_minute != null && reference.end_minute != null) {
    return `${reference.start_minute}–${reference.end_minute} minutes`;
  }
  return undefined;
}

function ClaimSegment({ claim }: Readonly<{ claim: Claim }>) {
  if (claim.verdict === "failed") {
    return (
      <span className="text-destructive" data-claim-state="failed">
        Claim unavailable: {claim.failure?.replaceAll("_", " ") ?? "calculation failed"}
      </span>
    );
  }
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-claim-state="supported">
      <span>{claim.value} {claim.unit}</span>
      {claim.evidence_refs.map((reference) => (
        <EvidenceLink
          fieldOrRange={fieldOrRange(reference)}
          group={reference.group}
          key={`${reference.group}:${reference.record_id}:${reference.field ?? reference.start_minute ?? ""}`}
          // Story 2.8 owns navigation. Supplying the activation seam now is a
          // deliberate inert state, not an EvidenceLink with neither prop.
          onActivate={() => undefined}
          record={reference.record_id}
          version={reference.scenario_version_id}
        />
      ))}
    </span>
  );
}

function AgentResponse({ item }: Readonly<{ item: AgentResponse }>) {
  return (
    <div aria-label="ShiftMind response" className="space-y-2">
      <p className="text-xs font-medium text-muted-foreground">ShiftMind</p>
      <p className="flex flex-wrap items-center gap-2 text-sm whitespace-pre-wrap">
        {item.response.segments.map((segment, index) =>
          segment.kind === "prose" ? (
            <span key={`prose-${index}`}>{segment.text}</span>
          ) : (
            <ClaimSegment claim={segment} key={`claim-${segment.result_id}-${index}`} />
          ),
        )}
      </p>
    </div>
  );
}

export function ActivityTimeline({ items }: Readonly<{ items: Timeline["items"] }>) {
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
      {unique.map((item) => (
        <li
          className="rounded-lg border bg-card p-3"
          data-activity-id={item.activity_id}
          key={item.activity_id}
        >
          {item.activity_type === "planner_message" ? (
            <div aria-label="Planner message">
              <p className="text-xs font-medium text-muted-foreground">You</p>
              <p className="text-sm whitespace-pre-wrap">{item.text}</p>
            </div>
          ) : (
            <AgentResponse item={item} />
          )}
        </li>
      ))}
    </ol>
  );
}
