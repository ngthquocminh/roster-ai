import type { Timeline } from "@/api/conversations";
import { EmptyState } from "@/components/primitives/EmptyState";

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
          <p className="text-sm whitespace-pre-wrap">{item.text}</p>
        </li>
      ))}
    </ol>
  );
}
