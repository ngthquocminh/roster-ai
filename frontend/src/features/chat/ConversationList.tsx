import { useRef, useState } from "react";
import { X } from "lucide-react";
import type { Conversation } from "@/api/conversations";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";

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
  onArchive,
  archivingIds,
  onFocusFallback,
}: Readonly<{
  conversations: Conversation[];
  selectedId: string;
  onSelect: (id: string) => void;
  onArchive: (id: string) => void;
  archivingIds: ReadonlySet<string>;
  onFocusFallback: () => void;
}>) {
  // Archiving has no "unarchive" UI in this pass, so it should not be one
  // accidental click — confirm first, same shape as
  // ApprovalDecisionDialog/ApprovalDecisionPanel's trigger-ref + restore-focus
  // pattern.
  const [confirming, setConfirming] = useState<Conversation | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const listRef = useRef<HTMLUListElement | null>(null);

  if (!conversations.length) return null;

  const restoreFocus = () => {
    setTimeout(() => {
      const trigger = triggerRef.current;
      // A committed archive removes the trigger from the DOM; focusing a
      // detached node silently drops focus to <body>. Fall back to the list,
      // and if archiving the last conversation just unmounted this whole
      // component (the empty-list early return below), fall back once more
      // to a target the caller guarantees stays mounted.
      if (trigger?.isConnected) trigger.focus();
      else if (listRef.current?.isConnected) listRef.current.focus();
      else onFocusFallback();
    });
  };

  const closeDialog = (open: boolean) => {
    if (!open) {
      setConfirming(null);
      restoreFocus();
    }
  };

  const confirmArchive = () => {
    if (!confirming) return;
    onArchive(confirming.id);
    setConfirming(null);
  };

  // A vertical wheel gesture over a horizontally-scrolling row does nothing
  // by default (the row has no vertical overflow, so the page scrolls
  // instead). Redirect the delta onto scrollLeft so the mouse wheel scrolls
  // the tab strip the way a trackpad's horizontal swipe already does.
  const handleWheel = (event: React.WheelEvent<HTMLUListElement>) => {
    if (event.deltaY === 0) return;
    event.currentTarget.scrollLeft += event.deltaY;
    event.preventDefault();
  };

  return (
    <nav aria-label="Conversations">
      {/* Single row, no wrap: overflow scrolls horizontally instead of
          growing the list downward. */}
      <ul
        className="scrollbar-thin flex flex-nowrap gap-2 overflow-x-auto"
        onWheel={handleWheel}
        ref={listRef}
        tabIndex={-1}
      >
        {conversations.map((conversation) => {
          const isSelected = selectedId === conversation.id;
          const shortId = conversation.id.slice(0, 8);
          return (
            <li className="flex shrink-0 items-center gap-1" key={conversation.id}>
              {/* Select and archive are SIBLING controls, never nested — a
                  button inside a button is invalid and would also merge
                  their accessible names. */}
              <Button
                aria-current={isSelected ? "page" : undefined}
                className="min-h-11 font-mono text-xs whitespace-nowrap"
                onClick={() => onSelect(conversation.id)}
                type="button"
                variant={isSelected ? "secondary" : "ghost"}
              >
                {label(conversation)}
              </Button>
              <Button
                aria-label={`Archive conversation ${shortId}`}
                className="min-h-11 min-w-11"
                disabled={archivingIds.has(conversation.id)}
                onClick={(event) => {
                  triggerRef.current = event.currentTarget;
                  setConfirming(conversation);
                }}
                size="icon"
                type="button"
                variant="ghost"
              >
                <X aria-hidden="true" />
              </Button>
            </li>
          );
        })}
      </ul>
      <Dialog onOpenChange={closeDialog} open={confirming !== null}>
        <DialogContent
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            restoreFocus();
          }}
        >
          <DialogHeader>
            <DialogTitle>Archive conversation</DialogTitle>
            <DialogDescription>
              {confirming
                ? `Archive ${label(confirming)}? It will no longer appear in this list.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <DialogClose asChild>
              <Button className="min-h-11" variant="outline">
                Cancel
              </Button>
            </DialogClose>
            <Button
              className="min-h-11"
              onClick={confirmArchive}
              type="button"
              variant="destructive"
            >
              Archive
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </nav>
  );
}
