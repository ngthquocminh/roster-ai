import type { Timeline } from "@/api/conversations";
export function ActivityTimeline({ items }: { items: Timeline["items"] }) {
  const unique = [...new Map(items.map((item) => [item.activity_id, item])).values()];
  if (!unique.length) return <p>Start a new conversation about this scenario—for example, ask about coverage, demand, or constraints.</p>;
  return <ol aria-label="Conversation activity">{unique.map((item) => <li key={item.activity_id}><p>{item.text}</p></li>)}</ol>;
}
