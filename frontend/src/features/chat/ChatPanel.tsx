import { MessageSquare, PanelRightClose, PanelRightOpen } from "lucide-react";
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";
import { useLocation, useSearchParams } from "react-router";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { ChatView } from "./ChatView";

const STORAGE_KEY = "shiftmind.chat-panel-expanded";
// Max-width, not min-width: the test setup's matchMedia stub answers `false`
// to every query, so tests get the desktop layout by default.
const NARROW_QUERY = "(max-width: 1023px)";

function isNarrowViewport(): boolean {
  return typeof window !== "undefined"
    && typeof window.matchMedia === "function"
    && window.matchMedia(NARROW_QUERY).matches;
}

function readStoredExpanded(): boolean {
  try {
    return localStorage.getItem(STORAGE_KEY) !== "false";
  } catch {
    return true;
  }
}

function storeExpanded(expanded: boolean): void {
  try {
    localStorage.setItem(STORAGE_KEY, String(expanded));
  } catch {
    // Storage can be disabled; the panel then just resets to expanded.
  }
}

/** Where the planner is, ignoring the chat's own `?conversation=` writes. */
function pageKey(pathname: string, search: string): string {
  const params = new URLSearchParams(search);
  params.delete("conversation");
  return `${pathname}?${params.toString()}`;
}

/**
 * The scenario's chat, docked on the right of the workspace. While the
 * workspace is loaded it is only ever hidden, never unmounted, so the live
 * stream and unsaved Draft card edits survive collapsing and tab switches.
 *
 * Desktop: expanded pushes the workspace content aside; collapsed leaves a
 * slim rail. Below `lg`: an overlay drawer, closed on first render.
 */
export function ChatPanel({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const bodyId = useId();
  const toggleRef = useRef<HTMLButtonElement | null>(null);
  const location = useLocation();
  const [searchParams] = useSearchParams();
  // An empty `?conversation=` names nothing, so it requests nothing.
  const urlConversation = searchParams.get("conversation") || null;
  const urlConversationRef = useRef(urlConversation);
  urlConversationRef.current = urlConversation;

  const [narrow, setNarrow] = useState(isNarrowViewport);
  // A link naming a conversation (an old Chat URL, Return to claim) opens the
  // panel from the FIRST render: ChatView's focus restoration runs before any
  // effect here could expand it, and focusing inside `hidden` silently fails.
  const [expanded, setExpanded] = useState(
    () => urlConversation !== null || (!isNarrowViewport() && readStoredExpanded()),
  );

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const query = window.matchMedia(NARROW_QUERY);
    const apply = (matches: boolean) => {
      setNarrow(matches);
      setExpanded(!matches && (readStoredExpanded() || urlConversationRef.current !== null));
    };
    // Re-sync in case the viewport crossed the breakpoint before subscribing.
    if (query.matches !== isNarrowViewport()) apply(query.matches);
    const update = (event: MediaQueryListEvent) => apply(event.matches);
    query.addEventListener("change", update);
    return () => query.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (urlConversation !== null) setExpanded(true);
  }, [urlConversation]);

  // The narrow drawer covers the page, so a navigation from inside it (an
  // Evidence link) must get out of the way of the destination.
  const currentPage = pageKey(location.pathname, location.search);
  const lastPage = useRef(currentPage);
  useEffect(() => {
    if (lastPage.current === currentPage) return;
    lastPage.current = currentPage;
    if (narrow) setExpanded(false);
  }, [currentPage, narrow]);

  // The toggle lives in ChatView's title row while expanded and on the rail
  // while collapsed, so each switch swaps the element. Focus follows it once
  // the new one is committed, or a keyboard user would drop to <body>.
  const refocusToggle = useRef(false);
  useEffect(() => {
    if (!refocusToggle.current) return;
    refocusToggle.current = false;
    toggleRef.current?.focus();
  }, [expanded]);

  const toggle = () => {
    const next = !expanded;
    refocusToggle.current = true;
    setExpanded(next);
    // The drawer's open state is transient; only the desktop choice persists.
    if (!narrow) storeExpanded(next);
  };

  const closeDrawerOnEscape = (event: KeyboardEvent) => {
    if (!narrow || !expanded || event.key !== "Escape") return;
    refocusToggle.current = true;
    setExpanded(false);
  };

  const toggleButton = (
    <Button
      aria-controls={bodyId}
      aria-expanded={expanded}
      aria-label={expanded ? "Collapse chat" : "Expand chat"}
      className={cn("min-h-11 min-w-11", expanded ? "" : "rounded-full shadow-lg lg:rounded-lg lg:shadow-none")}
      onClick={toggle}
      ref={toggleRef}
      type="button"
      variant={expanded ? "ghost" : "outline"}
    >
      {expanded ? (
        <PanelRightClose aria-hidden="true" />
      ) : (
        <>
          <MessageSquare aria-hidden="true" className="lg:hidden" />
          <PanelRightOpen aria-hidden="true" className="hidden lg:block" />
        </>
      )}
    </Button>
  );

  return (
    <aside
      aria-label="Chat panel"
      className={cn(
        "z-40 flex flex-col bg-background lg:static lg:z-auto lg:h-full lg:shrink-0 lg:border-l lg:border-border lg:shadow-none",
        expanded
          ? "fixed inset-y-0 right-0 w-full max-w-md border-l border-border shadow-xl lg:w-[420px] lg:max-w-none"
          : "fixed right-4 bottom-4 lg:w-12 lg:items-center",
      )}
      onKeyDown={closeDrawerOnEscape}
    >
      {expanded ? null : <div className="lg:pt-2">{toggleButton}</div>}
      <div
        className="flex min-h-0 flex-1 flex-col px-4 pt-3 pb-4"
        hidden={!expanded}
        id={bodyId}
      >
        {/* Title, New conversation and the collapse toggle share one row. */}
        <ChatView headerActions={expanded ? toggleButton : null} scenarioId={scenarioId} />
      </div>
    </aside>
  );
}
