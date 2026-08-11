import { useEffect, useMemo, useRef, useState } from "react";

import { conversationEventsUrl, type Timeline } from "@/api/conversations";
import { useConversationTimeline } from "./useConversationTimeline";

export type ActivityItem = Timeline["items"][number];

/** The three states `ReconnectBanner` renders. `null` means "nothing has gone
 * wrong yet" and shows no banner at all — the component has no runtime guard
 * for a fourth value, so this hook must never invent one. */
export type ReconnectState = "disconnected" | "reconnecting" | "reconnected";

/** The minimal structural contract this hook uses. `EventSource` satisfies it,
 * and so can a test stub — which matters because **jsdom does not implement
 * `EventSource`**, so a hook that reached for the global would be untestable
 * and a polyfill dependency is not warranted for one seam (AR27). */
export type EventSourceLike = {
  addEventListener(type: string, listener: (event: Event) => void): void;
  removeEventListener(type: string, listener: (event: Event) => void): void;
  close(): void;
};
export type EventSourceConstructor = new (url: string) => EventSourceLike;

type CursorStorage = Pick<Storage, "getItem" | "setItem">;

/** Frames carry `event: planner_message_accepted`, and `onmessage` fires only
 * for the default `message` type — so a listener on that name is the only way
 * these frames are ever seen. It is also the only event type that exists: no
 * agent runs, nothing leaves `agent_queued`. */
export const PLANNER_MESSAGE_ACCEPTED = "planner_message_accepted";

/** Consecutive failed connections before giving up on the stream. Bounded so a
 * permanently rejected cursor cannot retry-loop forever. */
const MAX_CONSECUTIVE_FAILURES = 3;
const FALLBACK_POLL_INTERVAL_MS = 15_000;
/** Same window the timeline read uses; see the merge below (UX-DR24). */
const WINDOW_CAP = 200;
/** How long "Connection restored." stays visible before the banner clears
 * itself. Without this, a single transient blip leaves it mounted for the
 * rest of the conversation's lifetime — it is meant to confirm a recovery
 * just happened, not to describe the connection's state indefinitely. */
const RECOVERY_BANNER_MS = 5_000;
/** A hung connection never fires `error` — `readyState` stays OPEN and
 * nothing ever learns the socket died. AD-21's 15s comment heartbeat exists
 * on the wire for exactly this, but a plain `EventSource` gives JS no
 * callback for "a comment line arrived": the WHATWG parsing algorithm
 * discards them before dispatching anything, and Task 4 forbids emitting
 * them as a named `event:` to make them observable. The next best signal is
 * real activity — a data frame or the initial `open`. If neither has been
 * seen for this long, treat the connection as dead through the same path
 * `onError` uses. Deliberately generous (minutes, not seconds): a healthy,
 * quiet conversation can go this long with nothing to say, and this is a
 * coarse safety net against a silently stuck connection, not a true
 * liveness check — see the story's "Note for review" for what would be
 * required to do better (byte-level stream reading). */
const STALE_AFTER_MS = 120_000;
/** Delay before opening a *retry* connection, indexed by consecutive
 * failures so far (`failures - 1`, clamped to the last entry). The very
 * first connect (`attempt === 0`) is never delayed. Bounded and small: this
 * only softens the case where the server rejects a resumed cursor
 * synchronously, so up to `MAX_CONSECUTIVE_FAILURES` attempts would
 * otherwise fire back-to-back. */
const RECONNECT_BACKOFF_MS = [250, 750];

export const cursorStorageKey = (conversationId: string) =>
  `shiftmind.conversation-cursor.${conversationId}`;

function defaultEventSource(): EventSourceConstructor | null {
  return (globalThis as { EventSource?: EventSourceConstructor }).EventSource ?? null;
}

function defaultStorage(): CursorStorage | null {
  try {
    return globalThis.sessionStorage ?? null;
  } catch {
    return null;
  }
}

/**
 * Live conversation activity that survives a reconnect (AR21, UX-DR6, UX-DR20).
 *
 * Owns the event source, the resume cursor, the merge, the reconnect state
 * machine, and the labelled-polling fallback. It wraps `useConversationTimeline`
 * rather than sitting beside it because the fallback *is* a `refetchInterval` on
 * that query — two hooks would have to pass the degraded flag back and forth.
 */
export function useConversationStream(
  conversationId: string,
  options?: {
    eventSourceConstructor?: EventSourceConstructor | null;
    storage?: CursorStorage | null;
  },
) {
  const eventSourceConstructor =
    options?.eventSourceConstructor !== undefined
      ? options.eventSourceConstructor
      : defaultEventSource();
  const storage = options?.storage !== undefined ? options.storage : defaultStorage();

  const [failures, setFailures] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const [live, setLive] = useState<ActivityItem[]>([]);
  const [connection, setConnection] = useState<ReconnectState | null>(null);
  const cursorRef = useRef<string | null>(null);
  const newestRef = useRef<string | null>(null);

  const updatesAreDelayed = failures >= MAX_CONSECUTIVE_FAILURES;
  const timeline = useConversationTimeline(
    conversationId,
    updatesAreDelayed ? FALLBACK_POLL_INTERVAL_MS : false,
  );

  const items = timeline.data?.items;
  const newest = items && items.length > 0 ? items[items.length - 1].sequence : null;
  const ready = Boolean(conversationId) && timeline.isSuccess;

  // Switching conversations must not carry the previous one's cursor or its
  // accumulated frames across — the planner would resume a stream they are no
  // longer reading.
  useEffect(() => {
    cursorRef.current = null;
    setLive([]);
    setConnection(null);
    setFailures(0);
    setAttempt(0);
  }, [conversationId]);

  // Declared before the connect effect so the seed below always reads the
  // current value. Kept in a ref rather than a dependency: a timeline refetch
  // changes `newest` on every new message, and treating that as a reason to
  // tear down and re-open the stream would churn a healthy connection.
  useEffect(() => {
    newestRef.current = newest;
  }, [newest]);

  // `"reconnected"` is a confirmation, not an ongoing status — clear it back
  // to `null` (no banner) after it has had a chance to be seen, so a single
  // blip doesn't leave "Connection restored." on screen indefinitely.
  useEffect(() => {
    if (connection !== "reconnected") return;
    const timeout = setTimeout(() => {
      setConnection((state) => (state === "reconnected" ? null : state));
    }, RECOVERY_BANNER_MS);
    return () => clearTimeout(timeout);
  }, [connection]);

  useEffect(() => {
    if (!ready || !eventSourceConstructor || updatesAreDelayed) return;

    if (cursorRef.current === null) {
      // Seed from the timeline's newest item, **not** from 0. The timeline read
      // is tail-anchored and capped at 200, so a first connect at 0 would
      // replay the entire history that read deliberately truncated — every one
      // of those events arriving as a "new" frame. A cursor stored by an
      // earlier mount wins over it. Both absent (a conversation with no
      // activity at all) is the only case that connects with no cursor.
      const stored = storage?.getItem(cursorStorageKey(conversationId)) ?? null;
      cursorRef.current = stored ?? newestRef.current;
    }

    let source: EventSourceLike | null = null;
    let idleTimer: ReturnType<typeof setTimeout> | undefined;

    // Shared by the native `error` event and the idle watchdog below — a
    // stalled connection and a rejected one recover the same way: close,
    // mark disconnected, and let the next `attempt` re-open from the
    // persisted cursor.
    const forceReconnect = () => {
      source?.close();
      setConnection("disconnected");
      setFailures((count) => count + 1);
      setAttempt((count) => count + 1);
    };

    const resetIdleTimer = () => {
      clearTimeout(idleTimer);
      idleTimer = setTimeout(forceReconnect, STALE_AFTER_MS);
    };

    const onFrame = (event: Event) => {
      resetIdleTimer();
      const raw = (event as MessageEvent).data;
      let item: ActivityItem;
      try {
        item = JSON.parse(String(raw)) as ActivityItem;
      } catch {
        return;
      }
      if (typeof item?.activity_id !== "string" || typeof item?.sequence !== "string") return;
      // A string, always — never `Number(...)`. That is the whole reason Story
      // 2.3 serialized `sequence` as a string in the first place.
      cursorRef.current = item.sequence;
      try {
        storage?.setItem(cursorStorageKey(conversationId), item.sequence);
      } catch {
        // Storage can throw (quota exceeded, disabled in this context). The
        // resume cursor already advanced in memory, so the stream keeps
        // going; only a future remount would replay from an earlier point.
        // What must not happen is this activity failing to render because a
        // storage write failed.
      }
      setFailures(0);
      setLive((current) => [...current, item].slice(-WINDOW_CAP));
    };

    const onOpen = () => {
      resetIdleTimer();
      setFailures(0);
      // Only report recovery to someone who was told about the loss.
      setConnection((state) => (state === null ? null : "reconnected"));
    };

    const onError = () => {
      // A rejected cursor comes back as a non-200 that is not
      // `text/event-stream`, which per WHATWG fails an `EventSource`
      // permanently — `error` fires, `readyState` becomes CLOSED, no retry.
      // That is exactly what lets us re-establish from our own persisted
      // cursor: `EventSource` cannot set `Last-Event-ID` itself, so the new
      // source carries it as a query parameter instead.
      forceReconnect();
    };

    const connect = () => {
      if (attempt > 0) setConnection("reconnecting");
      source = new eventSourceConstructor(
        conversationEventsUrl(conversationId, cursorRef.current),
      );
      resetIdleTimer();
      source.addEventListener(PLANNER_MESSAGE_ACCEPTED, onFrame);
      source.addEventListener("open", onOpen);
      source.addEventListener("error", onError);
    };

    // Retries only — the first connect (`attempt === 0`) runs synchronously,
    // not through `setTimeout(fn, 0)`, which still defers to the next
    // macrotask and would make every other test in this file wait a tick
    // for no reason. `failures` isn't a dependency of this effect (adding it
    // would tear down and reopen a perfectly healthy connection the moment
    // it resets to 0 on the next successful frame); it's read here as a
    // plain closure value instead, which is safe because `forceReconnect`
    // always changes `attempt` and `failures` together, so this effect
    // never re-runs without also seeing the `failures` value that produced
    // this run.
    let connectTimer: ReturnType<typeof setTimeout> | undefined;
    if (attempt > 0) {
      const backoffMs = RECONNECT_BACKOFF_MS[Math.max(0, failures - 1)] ?? 0;
      connectTimer = setTimeout(connect, backoffMs);
    } else {
      connect();
    }

    return () => {
      clearTimeout(connectTimer);
      clearTimeout(idleTimer);
      source?.removeEventListener(PLANNER_MESSAGE_ACCEPTED, onFrame);
      source?.removeEventListener("open", onOpen);
      source?.removeEventListener("error", onError);
      source?.close();
    };
    // `failures` is deliberately excluded — see the comment above where it's
    // read. Adding it would tear down and reopen a healthy connection every
    // time it resets to 0 on a successful frame.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    ready,
    eventSourceConstructor,
    updatesAreDelayed,
    conversationId,
    attempt,
    storage,
  ]);

  const merged = useMemo(() => {
    const base = timeline.data?.items ?? [];
    const limit = timeline.data?.limit ?? WINDOW_CAP;
    // Merge by activity identity, never by position (UX-DR6). The sender's own
    // message is the proof: `useSendMessage` invalidates the timeline on
    // success, so it arrives twice — once from the refetch, once from the
    // stream — and exactly one card must render.
    const byId = new Map<string, ActivityItem>();
    for (const item of base) byId.set(item.activity_id, item);
    for (const item of live) byId.set(item.activity_id, item);
    const all = [...byId.values()];
    // Bounded to the same window the timeline read uses (UX-DR24): no
    // unbounded growth, and the "Showing the most recent N activities" copy
    // stays honest as live frames arrive.
    return all.length > limit ? all.slice(all.length - limit) : all;
  }, [timeline.data, live]);

  return { timeline, items: merged, connection, updatesAreDelayed };
}
