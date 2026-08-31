import { render, screen } from "@testing-library/react";
import { act } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useConversationTimeline", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useConversationTimeline")>()),
  useConversationTimeline: vi.fn(),
}));

import { ReconnectBanner } from "@/components/primitives/ReconnectBanner";
import { ActivityTimeline } from "@/features/chat/ActivityTimeline";
import { useConversationTimeline } from "@/hooks/useConversationTimeline";
import {
  APPROVAL_REQUEST,
  cursorStorageKey,
  PLANNER_MESSAGE_ACCEPTED,
  STREAMED_ACTIVITY_EVENTS,
  useConversationStream,
  type EventSourceLike,
} from "./useConversationStream";

const mockTimeline = useConversationTimeline as unknown as ReturnType<typeof vi.fn>;

const CONVERSATION = "77777777-7777-7777-7777-777777777777";
const SCENARIO = "33333333-3333-3333-3333-333333333333";
const VERSION = "44444444-4444-4444-4444-444444444444";
const EXISTING = "aaaaaaaa-1111-1111-1111-111111111111";
const ARRIVING = "bbbbbbbb-2222-2222-2222-222222222222";

it("subscribes to the persisted approval lifecycle discriminant", () => {
  expect(STREAMED_ACTIVITY_EVENTS).toContain(APPROVAL_REQUEST);
});

function activity(activityId: string, text: string, sequence: string) {
  return {
    schema_version: "1",
    activity_id: activityId,
    activity_type: "planner_message" as const,
    conversation_id: CONVERSATION,
    conversation_resource_version: 2,
    scenario_id: SCENARIO,
    scenario_version_id: VERSION,
    occurred_at: "2026-08-11T00:00:00Z",
    message_id: activityId,
    text,
    sequence,
  };
}

/** jsdom implements no `EventSource`, which is exactly why the hook takes the
 * constructor as a parameter. This stub is the whole seam. */
class StubEventSource implements EventSourceLike {
  static instances: StubEventSource[] = [];
  readonly url: string;
  readonly listeners = new Map<string, Set<(event: Event) => void>>();
  closed = false;

  constructor(url: string) {
    this.url = url;
    StubEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: Event) => void): void {
    if (!this.listeners.has(type)) this.listeners.set(type, new Set());
    this.listeners.get(type)!.add(listener);
  }

  removeEventListener(type: string, listener: (event: Event) => void): void {
    this.listeners.get(type)?.delete(listener);
  }

  close(): void {
    this.closed = true;
  }

  emit(type: string, event: Partial<MessageEvent> = {}): void {
    act(() => {
      for (const listener of [...(this.listeners.get(type) ?? [])]) {
        listener(event as Event);
      }
    });
  }

  static latest(): StubEventSource {
    const found = StubEventSource.instances.at(-1);
    if (!found) throw new Error("no event source was opened");
    return found;
  }
}

/** Every banner state the hook has rendered, in order. Recorded rather than
 * sampled: `disconnected` and `reconnecting` land in consecutive commits, so a
 * single assertion after the fact can only ever see the second of them. */
let renderedStates: (string | null)[] = [];

/** Renders exactly what ChatView renders from the hook, so these assertions are
 * about visible output rather than about internal state. */
function Harness({ conversationId = CONVERSATION }: { conversationId?: string }) {
  const stream = useConversationStream(conversationId, {
    eventSourceConstructor: StubEventSource,
  });
  renderedStates.push(stream.connection);
  return (
    <>
      {stream.connection ? <ReconnectBanner state={stream.connection} /> : null}
      <ActivityTimeline navigate={vi.fn()} items={stream.items} />
      {stream.updatesAreDelayed ? (
        <p role="status">
          Live updates are unavailable. This conversation is refreshing on a delay.
        </p>
      ) : null}
    </>
  );
}

function timelineWith(items: ReturnType<typeof activity>[], limit = 200) {
  return {
    data: {
      conversation_id: CONVERSATION,
      resource_version: 2,
      latest_agent_run_status: "agent_queued",
      items,
      limit,
      has_more: false,
    },
    error: null,
    isError: false,
    isPending: false,
    isSuccess: true,
    refetch: vi.fn(),
  };
}

beforeEach(() => {
  vi.useRealTimers();
  mockTimeline.mockReset();
  StubEventSource.instances = [];
  renderedStates = [];
  sessionStorage.clear();
  mockTimeline.mockReturnValue(timelineWith([activity(EXISTING, "Check coverage", "7")]));
});

describe("useConversationStream", () => {
  it("renders one card when a replayed event is already in the timeline", () => {
    render(<Harness />);

    StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, {
      data: JSON.stringify(activity(EXISTING, "Check coverage", "7")),
    });

    // The sender's own message arrives twice — once from `useSendMessage`'s
    // invalidation, once from the stream. Merging by activity identity rather
    // than by position is what keeps that one card (UX-DR6).
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("renders a newly arriving activity alongside the restored window", () => {
    render(<Harness />);

    StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, {
      data: JSON.stringify(activity(ARRIVING, "Night shift is short", "8")),
    });

    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(screen.getByText("Night shift is short")).toBeInTheDocument();
  });

  it("seeds the first cursor from the timeline's newest item, never from zero", () => {
    render(<Harness />);

    // Connecting at 0 would replay the entire history the tail-anchored,
    // 200-capped timeline read deliberately truncated — as "new" frames.
    expect(StubEventSource.latest().url).toContain(
      `last_event_id=${encodeURIComponent(`${CONVERSATION}:7`)}`,
    );
  });

  it("connects with no cursor only when the conversation has no activity at all", () => {
    mockTimeline.mockReturnValue(timelineWith([]));

    render(<Harness />);

    expect(StubEventSource.latest().url).not.toContain("last_event_id");
  });

  it("re-establishes a rejected connection with its own stored cursor", () => {
    vi.useFakeTimers();
    render(<Harness />);
    StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, {
      data: JSON.stringify(activity(ARRIVING, "Night shift is short", "8")),
    });
    const rejected = StubEventSource.latest();

    rejected.emit("error");
    // The retry is deliberately backed off rather than immediate (bounded
    // reconnect-attempt backoff); advance past it to let the new source open.
    act(() => {
      vi.advanceTimersByTime(1_000);
    });

    // The dead source is closed, not left retry-looping on a poisoned header,
    // and the replacement carries the cursor we persisted ourselves.
    expect(rejected.closed).toBe(true);
    expect(StubEventSource.instances).toHaveLength(2);
    expect(StubEventSource.latest().url).toContain(
      `last_event_id=${encodeURIComponent(`${CONVERSATION}:8`)}`,
    );
    vi.useRealTimers();
  });

  it("backs off before retrying instead of reconnecting immediately", () => {
    // Bounded so a synchronously-rejected cursor can't burst three
    // back-to-back connection attempts at a possibly-struggling backend.
    vi.useFakeTimers();
    render(<Harness />);
    StubEventSource.latest().emit("error");

    expect(StubEventSource.instances).toHaveLength(1);

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(StubEventSource.instances).toHaveLength(2);
    vi.useRealTimers();
  });

  it("walks the banner through all three reconnect states and no fourth one", () => {
    vi.useFakeTimers();
    render(<Harness />);
    // A healthy stream shows no banner at all.
    expect(renderedStates.every((state) => state === null)).toBe(true);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();

    StubEventSource.latest().emit("error");
    // `disconnected` commits immediately; `reconnecting` only follows once
    // the backoff elapses and the retry actually opens.
    expect(renderedStates).toContain("disconnected");

    act(() => {
      vi.advanceTimersByTime(1_000);
    });
    expect(screen.getByText("Reconnecting…")).toBeInTheDocument();

    StubEventSource.latest().emit("open");
    expect(screen.getByText("Connection restored.")).toBeInTheDocument();

    expect(new Set(renderedStates)).toEqual(
      new Set([null, "disconnected", "reconnecting", "reconnected"]),
    );
    vi.useRealTimers();
  });

  it("leaves the banner in a state ReconnectBanner can actually render", () => {
    vi.useFakeTimers();
    render(<Harness />);
    for (let attempt = 0; attempt < 4; attempt += 1) {
      StubEventSource.latest().emit("error");
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
    }

    // `ReconnectBanner`'s COPY lookup has no runtime guard for a value outside
    // its three-member union, and this hook is its first real caller — so a
    // fourth state invented here would render `undefined.title`.
    for (const state of renderedStates) {
      expect(["disconnected", "reconnecting", "reconnected", null]).toContain(state);
    }
    vi.useRealTimers();
  });

  it("falls back to visibly labelled polling after repeated failures", () => {
    vi.useFakeTimers();
    render(<Harness />);

    for (let attempt = 0; attempt < 3; attempt += 1) {
      StubEventSource.latest().emit("error");
      act(() => {
        vi.advanceTimersByTime(1_000);
      });
    }

    // AC2 requires the fallback; silent polling is a failure of it.
    expect(
      screen.getByText(/Live updates are unavailable\. This conversation is refreshing on a delay\./),
    ).toBeInTheDocument();
    // The timeline query is now polling on an interval rather than idle.
    expect(mockTimeline).toHaveBeenLastCalledWith(CONVERSATION, 15_000);
    // And it stopped opening new sources rather than retrying forever.
    expect(StubEventSource.instances).toHaveLength(3);
    vi.useRealTimers();
  });

  it("keeps the stored cursor across a remount", () => {
    const first = render(<Harness />);
    StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, {
      data: JSON.stringify(activity(ARRIVING, "Night shift is short", "8")),
    });
    expect(sessionStorage.getItem(cursorStorageKey(CONVERSATION))).toBe("8");
    first.unmount();

    render(<Harness />);

    // The timeline's newest item is still sequence 7; the persisted cursor is
    // what stops those events being replayed a second time.
    expect(StubEventSource.latest().url).toContain(
      `last_event_id=${encodeURIComponent(`${CONVERSATION}:8`)}`,
    );
  });

  it("keeps the merged window bounded rather than growing without limit", () => {
    mockTimeline.mockReturnValue(
      timelineWith([activity(EXISTING, "Check coverage", "1")], 3),
    );
    render(<Harness />);

    for (const [index, sequence] of ["2", "3", "4"].entries()) {
      StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, {
        data: JSON.stringify(activity(`cccccccc-${index}-0000-0000-000000000000`, `later ${sequence}`, sequence)),
      });
    }

    // Capped at the timeline's own window (UX-DR24): no unbounded growth, and
    // the "Showing the most recent N activities" copy stays honest.
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
    expect(screen.queryByText("Check coverage")).not.toBeInTheDocument();
  });

  it("ignores a frame whose payload is not a usable activity", () => {
    render(<Harness />);

    StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, { data: "not json" });
    StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, { data: '{"sequence":9}' });

    // A malformed frame must not corrupt the cursor or the rendered window.
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(sessionStorage.getItem(cursorStorageKey(CONVERSATION))).toBeNull();
  });

  it("treats prolonged silence as a stalled connection and re-establishes", () => {
    // A hung connection never fires `error` — `readyState` stays OPEN and the
    // stub, like a real `EventSource`, would never emit anything on its own.
    // Only the idle watchdog can recover it, and it does so through the same
    // reconnect path `onError` uses.
    vi.useFakeTimers();
    render(<Harness />);
    const stalled = StubEventSource.latest();

    act(() => {
      // Past the 120s stale threshold — fires the idle watchdog.
      vi.advanceTimersByTime(120_000);
    });
    act(() => {
      // The watchdog's `forceReconnect` only schedules the retry's own
      // backoff once React flushes the resulting effect re-run, which
      // happens after this `act()` callback returns above — so the backoff
      // needs its own separate advance, not more of the same one.
      vi.advanceTimersByTime(1_000);
    });

    expect(stalled.closed).toBe(true);
    expect(StubEventSource.instances).toHaveLength(2);
    vi.useRealTimers();
  });

  it("does not treat a quiet-but-healthy stream as stalled", () => {
    vi.useFakeTimers();
    render(<Harness />);
    const first = StubEventSource.latest();

    act(() => {
      vi.advanceTimersByTime(60_000);
    });
    // Halfway to the stale threshold: still the same, still-open connection.
    expect(StubEventSource.instances).toHaveLength(1);

    act(() => {
      StubEventSource.latest().emit(PLANNER_MESSAGE_ACCEPTED, {
        data: JSON.stringify(activity(ARRIVING, "Night shift is short", "8")),
      });
      vi.advanceTimersByTime(90_000);
    });
    // A frame within the window resets the watchdog, so 90s more (150s total,
    // past the original 120s threshold) still doesn't force a reconnect.
    expect(first.closed).toBe(false);
    expect(StubEventSource.instances).toHaveLength(1);
    vi.useRealTimers();
  });

  it("opens nothing when no EventSource implementation is available", () => {
    function Bare() {
      const stream = useConversationStream(CONVERSATION, {
        eventSourceConstructor: null,
      });
      return <ActivityTimeline navigate={vi.fn()} items={stream.items} />;
    }

    render(<Bare />);

    // jsdom's own environment: the timeline still restores, the stream simply
    // never opens.
    expect(StubEventSource.instances).toHaveLength(0);
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });
});
