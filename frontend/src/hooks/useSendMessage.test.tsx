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
});
