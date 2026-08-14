import type { Timeline } from "@/api/conversations";
import { EmptyState } from "@/components/primitives/EmptyState";
import { EvidenceLink } from "@/components/primitives/EvidenceLink";

type Activity = Timeline["items"][number];
type AgentResponse = Extract<Activity, { activity_type: "agent_response" }>;
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

function ClaimSegment({ claim }: Readonly<{ claim: Claim }>) {
  if (claim.verdict === "failed") {
    return (
      <span className="text-destructive" data-claim-state="failed">
        Claim unavailable: {claim.failure?.replaceAll("_", " ") ?? "calculation failed"}
      </span>
    );
  }
  const subject = claimSubject(claim);
  return (
    <span className="inline-flex flex-wrap items-center gap-2" data-claim-state="supported">
      {/* Exactness is this feature's whole premise, so a raw float repr
          (90.00000000000001) is not acceptable output. Volume demand carries
          float amounts throughout the fixture, so this is reachable, not
          theoretical. Integers keep rendering unchanged. */}
      <span>
        {Number.isInteger(claim.value) ? claim.value : Number(claim.value).toFixed(2)}{" "}
        {claim.unit}
        {subject ? <span className="text-muted-foreground"> ({subject})</span> : null}
      </span>
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
  // A failed or timed-out run persists a response with no segments, which is
  // truthful — it produced no visible content. Rendering it as an empty bubble
  // under the ShiftMind label reads as the assistant having said nothing at
  // all. The full failure taxonomy is Story 2.9's; this is only the neutral
  // placeholder that keeps an empty record legible.
  if (!item.response.segments.length) {
    return (
      <div aria-label="ShiftMind response" className="space-y-2">
        <p className="text-xs font-medium text-muted-foreground">ShiftMind</p>
        <p className="text-sm text-destructive" data-response-state="unavailable">
          This turn did not complete. No answer was saved.
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
