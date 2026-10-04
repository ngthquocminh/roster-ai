import { useEffect, useRef, useState } from "react";
import { MessageSquare, X } from "lucide-react";
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

/** Fraction of each wheel step applied to the strip; a full step jumped ~3 tabs. */
const WHEEL_DAMPING = 0.35;
/** DOM_DELTA_LINE wheels (Firefox) report lines, not pixels. */
const LINE_HEIGHT_PX = 16;

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
  const hasConversations = conversations.length > 0;

  // A vertical wheel gesture over the horizontally-scrolling strip scrolls the
  // strip instead, and ONLY the strip. A native listener, not React's
  // `onWheel`: React registers wheel listeners as passive, so its
  // `preventDefault()` was ignored and the panel/page scrolled along with it.
  // At either end the gesture is released so the page can still scroll.
  useEffect(() => {
    const list = listRef.current;
    if (!list) return;
    const handleWheel = (event: WheelEvent) => {
      if (event.deltaY === 0 || list.scrollWidth <= list.clientWidth) return;
      const unit = event.deltaMode === WheelEvent.DOM_DELTA_LINE ? LINE_HEIGHT_PX : 1;
      const delta = event.deltaY * unit * WHEEL_DAMPING;
      const atStart = list.scrollLeft <= 0;
      const atEnd = list.scrollLeft + list.clientWidth >= list.scrollWidth - 1;
      if ((delta < 0 && atStart) || (delta > 0 && atEnd)) return;
      event.preventDefault();
      list.scrollLeft += delta;
    };
    list.addEventListener("wheel", handleWheel, { passive: false });
    return () => list.removeEventListener("wheel", handleWheel);
  }, [hasConversations]);

  if (!hasConversations) return null;

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

  return (
    <nav aria-label="Conversations">
      {/* Browser-style tab strip: one row, no wrap, overflow scrolls
          horizontally. The selected tab sits on the strip's baseline (-mb-px
          covers the border) so it reads as attached to the content below. */}
      <ul
        className="scrollbar-thin flex flex-nowrap items-end gap-0.5 overflow-x-auto overflow-y-hidden border-b border-border px-1"
        ref={listRef}
        tabIndex={-1}
      >
        {conversations.map((conversation) => {
          const isSelected = selectedId === conversation.id;
          const shortId = conversation.id.slice(0, 8);
          return (
            <li
              className={`-mb-px flex max-w-56 shrink-0 items-center rounded-t-lg border border-b-0 pr-0.5 transition-colors ${
                isSelected
                  ? "border-border bg-background text-foreground"
                  : "border-transparent bg-muted/60 text-muted-foreground hover:bg-muted hover:text-foreground"
              }`}
              key={conversation.id}
            >
              {/* Select and archive are SIBLING controls, never nested — a
                  button inside a button is invalid and would also merge
                  their accessible names. */}
              <Button
                aria-current={isSelected ? "page" : undefined}
                className="min-h-11 min-w-0 justify-start gap-2 rounded-none rounded-tl-lg pr-1 pl-3 text-sm whitespace-nowrap text-inherit hover:bg-transparent"
                onClick={() => onSelect(conversation.id)}
                type="button"
                variant="ghost"
              >
                <MessageSquare aria-hidden="true" className="size-3.5 shrink-0" />
                <span className="truncate">{label(conversation)}</span>
              </Button>
              <Button
                aria-label={`Archive conversation ${shortId}`}
                className="group/close min-h-11 min-w-9 rounded-full text-muted-foreground hover:bg-transparent hover:text-foreground"
                disabled={archivingIds.has(conversation.id)}
                onClick={(event) => {
                  triggerRef.current = event.currentTarget;
                  setConfirming(conversation);
                }}
                size="icon"
                type="button"
                variant="ghost"
              >
                {/* Chrome-like close: a small round hover chip inside a
                    full-height hit target. */}
                <span className="flex size-5 items-center justify-center rounded-full group-hover/close:bg-foreground/10">
                  <X aria-hidden="true" className="size-3.5" />
                </span>
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
