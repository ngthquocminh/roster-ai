import type { Conversation } from "@/api/conversations";
import { Button } from "@/components/ui/button";

/**
 * Conversation labels are derived from the conversation's own identity, never
 * from its position in the list. The list is ordered newest-first, so a
 * positional label ("Conversation 1") renames every existing conversation the
 * moment a new one is created — destabilising the only human-readable handle
 * for AC2's "chooses a prior conversation".
 */
function label(conversation: Conversation): string {
  return `Conversation ${conversation.id.slice(0, 8)}`;
}

export function ConversationList({
  conversations,
  selectedId,
  onSelect,
}: Readonly<{
  conversations: Conversation[];
  selectedId: string;
  onSelect: (id: string) => void;
}>) {
  if (!conversations.length) return null;
  return (
    <nav aria-label="Conversations">
      <ul className="flex flex-wrap gap-2">
        {conversations.map((conversation) => {
          const isSelected = selectedId === conversation.id;
          return (
            <li key={conversation.id}>
              <Button
                aria-current={isSelected ? "page" : undefined}
                className="min-h-11 font-mono text-xs"
                onClick={() => onSelect(conversation.id)}
                type="button"
                variant={isSelected ? "secondary" : "ghost"}
              >
                {label(conversation)}
              </Button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}
