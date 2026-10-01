/**
 * Code review of story-5.11: the stream never carries `latest_agent_run_status`,
 * so the timeline itself polls while a turn is in flight -- otherwise a reload
 * mid-turn leaves the Draft card's controls disabled indefinitely.
 */
import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/conversations", () => ({ getConversationTimeline: vi.fn() }));

import { getConversationTimeline } from "@/api/conversations";
import {
  conversationTimelineKey,
  IN_FLIGHT_POLL_INTERVAL_MS,
  useConversationTimeline,
} from "./useConversationTimeline";

const ID = "bbbbbbbb-0000-0000-0000-000000000000";

async function intervalFor(status: string | null, fallback: number | false = false) {
  const queryClient = new QueryClient();
  const wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  vi.mocked(getConversationTimeline).mockResolvedValue({ latest_agent_run_status: status, items: [] } as never);
  const { result } = renderHook(() => useConversationTimeline(ID, fallback), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  const query = queryClient.getQueryCache().find({ queryKey: conversationTimelineKey(ID) })!;
  // The observer's options carry `refetchInterval`; the query's own do not.
  const option = query.observers[0].options.refetchInterval;
  const value = typeof option === "function" ? option(query as never) : option;
  queryClient.clear();
  return value;
}

describe("useConversationTimeline", () => {
  it.each([
    ["agent_queued", IN_FLIGHT_POLL_INTERVAL_MS],
    ["agent_running", IN_FLIGHT_POLL_INTERVAL_MS],
    ["agent_completed", false],
    [null, false],
  ])("polls while %s is in flight, and only then", async (status, expected) => {
    expect(await intervalFor(status)).toBe(expected);
  });

  it("keeps the stream's labelled fallback interval whatever the status", async () => {
    expect(await intervalFor("agent_completed", 15_000)).toBe(15_000);
  });
});
