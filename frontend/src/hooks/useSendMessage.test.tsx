import type { PropsWithChildren } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

vi.mock("@/api/conversations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/api/conversations")>()),
  sendMessage: vi.fn(),
  executeTurn: vi.fn(),
}));

import { executeTurn, sendMessage, type Timeline } from "@/api/conversations";
import { conversationTimelineKey } from "./useConversationTimeline";
import { useSendMessage } from "./useSendMessage";

const mockSend = vi.mocked(sendMessage);
const mockExecute = vi.mocked(executeTurn);

describe("useSendMessage", () => {
  it("exposes queued state before executing the accepted run", async () => {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    queryClient.setQueryData<Timeline>(conversationTimelineKey("conversation-1"), {
      conversation_id: "conversation-1",
      resource_version: 1,
      latest_agent_run_status: null,
      latest_agent_run_status_reason: null,
      items: [],
      limit: 200,
      has_more: false,
    });
    const activity = {
      schema_version: "1",
      activity_id: "11111111-1111-1111-1111-111111111111",
      activity_type: "planner_message" as const,
      conversation_id: "conversation-1",
      conversation_resource_version: 2,
      scenario_id: "scenario-1",
      scenario_version_id: "version-1",
      occurred_at: "2026-08-13T00:00:00Z",
      message_id: "22222222-2222-2222-2222-222222222222",
      text: "Check coverage",
      sequence: "1",
    };
    mockSend.mockResolvedValue({
      activity,
      resource_version: 2,
      agent_run_status: "agent_queued",
      sequence: "1",
      agent_run_id: "run-1",
    });
    let releaseExecute!: () => void;
    mockExecute.mockImplementation(
      () => new Promise((resolve) => {
        releaseExecute = () => resolve({
          activity: { ...activity, activity_type: "agent_response", response: { schema_version: "1", scenario_version_id: "version-1", segments: [] } } as never,
          resource_version: 3,
          agent_run_status: "agent_completed",
          sequence: "2",
          agent_run_id: "run-1",
        });
      }),
    );
    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useSendMessage("conversation-1", "scenario-1"), { wrapper });

    act(() => result.current.mutate({ text: "Check coverage" }));
    await waitFor(() => expect(mockExecute).toHaveBeenCalledWith("conversation-1", "run-1"));
    expect(
      queryClient.getQueryData<Timeline>(conversationTimelineKey("conversation-1"))
        ?.latest_agent_run_status,
    ).toBe("agent_queued");
    releaseExecute();
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });
  it("refetches the timeline when executeTurn fails so a queued turn cannot wedge", async () => {
    // The optimistic write has already put the accepted message and
    // `agent_queued` into the cache. Invalidating only on success left a
    // rejected execute showing a queued turn that never refetched and never
    // resolved -- no rollback, no retry, no resume.
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    queryClient.setQueryData<Timeline>(conversationTimelineKey("conversation-1"), {
      conversation_id: "conversation-1",
      resource_version: 1,
      latest_agent_run_status: null,
      latest_agent_run_status_reason: null,
      items: [],
      limit: 200,
      has_more: false,
    });
    const invalidated = vi.spyOn(queryClient, "invalidateQueries");
    mockSend.mockResolvedValue({
      activity: {
        schema_version: "1",
        activity_id: "33333333-3333-3333-3333-333333333333",
        activity_type: "planner_message" as const,
        conversation_id: "conversation-1",
        conversation_resource_version: 2,
        scenario_id: "scenario-1",
        scenario_version_id: "version-1",
        occurred_at: "2026-08-13T00:00:00Z",
        message_id: "44444444-4444-4444-4444-444444444444",
        text: "Check coverage",
        sequence: "1",
      },
      resource_version: 2,
      agent_run_status: "agent_queued",
      sequence: "1",
      agent_run_id: "run-1",
    } as never);
    mockExecute.mockRejectedValue({ status: 409, code: "agent_run_not_queued" });

    const wrapper = ({ children }: PropsWithChildren) => (
      <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
    );
    const { result } = renderHook(() => useSendMessage("conversation-1", "scenario-1"), { wrapper });

    act(() => result.current.mutate({ text: "Check coverage" }));

    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(invalidated).toHaveBeenCalledWith({
      queryKey: conversationTimelineKey("conversation-1"),
    });
  });
});
