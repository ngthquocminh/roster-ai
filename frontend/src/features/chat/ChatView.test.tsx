import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { createMemoryRouter, RouterProvider } from "react-router";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/hooks/useConversations", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useConversations")>()),
  useConversations: vi.fn(),
}));
vi.mock("@/hooks/useConversationTimeline", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/hooks/useConversationTimeline")>()),
  useConversationTimeline: vi.fn(),
}));
vi.mock("@/hooks/useScenarioContext", () => ({ useScenarioContext: vi.fn() }));
vi.mock("@/hooks/useSendMessage", () => ({ useSendMessage: vi.fn() }));
vi.mock("@/api/conversations", () => ({ createConversation: vi.fn(), executeTurn: vi.fn(), sendMessage: vi.fn() }));

import { createConversation, executeTurn, sendMessage } from "@/api/conversations";
import { originElementId, rememberOrigin } from "@/features/evidence/origin";
import { useConversations } from "@/hooks/useConversations";
import { useConversationTimeline } from "@/hooks/useConversationTimeline";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { useSendMessage } from "@/hooks/useSendMessage";
import { ChatView } from "./ChatView";

const mockConversations = useConversations as unknown as ReturnType<typeof vi.fn>;
const mockTimeline = useConversationTimeline as unknown as ReturnType<typeof vi.fn>;
const mockContext = useScenarioContext as unknown as ReturnType<typeof vi.fn>;
const mockSend = useSendMessage as unknown as ReturnType<typeof vi.fn>;
const mockCreate = createConversation as unknown as ReturnType<typeof vi.fn>;
const mockExecute = executeTurn as unknown as ReturnType<typeof vi.fn>;
const mockSendMessage = sendMessage as unknown as ReturnType<typeof vi.fn>;
// The send mutation ChatView can actually reach. `sendMessage`/`executeTurn` are
// only called from inside `useSendMessage`, which this file mocks wholesale, so
// asserting on those two alone could never fail.
let mockSendMutate: ReturnType<typeof vi.fn>;

const SCENARIO = "33333333-3333-3333-3333-333333333333";
const VERSION = "44444444-4444-4444-4444-444444444444";
const OLDER = "aaaaaaaa-0000-0000-0000-000000000000";
const NEWER = "bbbbbbbb-0000-0000-0000-000000000000";

function conversation(id: string) {
  return {
    id,
    scenario_id: SCENARIO,
    scenario_version_id: VERSION,
    resource_version: 1,
  };
}

function activity(id: string, text: string, sequence: string) {
  return {
    schema_version: "1",
    activity_id: id,
    activity_type: "planner_message" as const,
    conversation_id: NEWER,
    conversation_resource_version: 2,
    scenario_id: SCENARIO,
    scenario_version_id: VERSION,
    occurred_at: "2026-08-10T00:00:00Z",
    message_id: id,
    text,
    sequence,
  };
}

function renderChat(initialEntry = `/scenarios/${SCENARIO}`) {
  const router = createMemoryRouter(
    [{ path: "/scenarios/:scenarioId", element: <ChatView scenarioId={SCENARIO} /> }],
    { initialEntries: [initialEntry] },
  );
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
}

beforeEach(() => {
  sessionStorage.clear();
  mockConversations.mockReset();
  mockTimeline.mockReset();
  mockContext.mockReset();
  mockSend.mockReset();
  mockCreate.mockReset();
  mockExecute.mockReset();
  mockSendMessage.mockReset();
  mockContext.mockReturnValue({ data: { scenario_version_id: VERSION } });
  mockSendMutate = vi.fn();
  mockSend.mockReturnValue({ isPending: false, mutateAsync: mockSendMutate });
  mockConversations.mockReturnValue({
    data: { items: [conversation(NEWER), conversation(OLDER)], limit: 100, has_more: false },
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });
  mockTimeline.mockReturnValue({
    data: {
      conversation_id: NEWER,
      resource_version: 2,
      latest_agent_run_status: "agent_queued",
      items: [activity("11111111-1111-1111-1111-111111111111", "Check coverage", "1")],
      limit: 200,
      has_more: false,
    },
    error: null,
    isError: false,
    isPending: false,
    refetch: vi.fn(),
  });
});

describe("ChatView", () => {
  it("restores the exact invoking evidence link once without resending or regenerating", async () => {
    const agentActivityId = "88888888-8888-4888-8888-888888888888";
    const origin = { conversationId: NEWER, activityId: agentActivityId, segmentIndex: 0, refIndex: 0 };
    const agentResponse = {
      schema_version: "1",
      activity_id: agentActivityId,
      activity_type: "agent_response" as const,
      conversation_id: NEWER,
      conversation_resource_version: 3,
      scenario_id: SCENARIO,
      scenario_version_id: VERSION,
      occurred_at: "2026-08-15T00:00:00Z",
      sequence: "3",
      response: {
        schema_version: "1",
        scenario_version_id: VERSION,
        segments: [{
          schema_version: "1",
          kind: "claim" as const,
          metric: "required_headcount_minutes" as const,
          arguments: { schema_version: "1" },
          result_id: "result-1",
          value: 12,
          unit: "workers" as const,
          verdict: "supported" as const,
          failure: null,
          evidence_refs: [{
            schema_version: "1",
            scenario_version_id: VERSION,
            checksum_algorithm: "sha256",
            checksum_schema_version: "1",
            checksum_digest: "a".repeat(64),
            producing_run_version: null,
            baseline_schedule_version: null,
            group: "demand" as const,
            record_id: "demand-1",
            field: "amount",
            start_minute: 0,
            end_minute: 30,
          }],
        }],
      },
    };
    mockTimeline.mockReturnValue({
      data: { conversation_id: NEWER, resource_version: 3, latest_agent_run_status: null, items: [agentResponse], limit: 200, has_more: false },
      error: null, isError: false, isPending: false, refetch: vi.fn(),
    });
    rememberOrigin(origin);
    const router = renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    const evidence = await screen.findByRole("button", { name: /Evidence: demand demand-1/ });
    await waitFor(() => expect(evidence).toHaveFocus());
    expect(evidence).toHaveAttribute("id", originElementId(origin));
    expect(router.state.location.pathname).toBe(`/scenarios/${SCENARIO}`);
    expect(router.state.location.search).toBe(`?conversation=${NEWER}`);
    // AC1: returning does not resend, regenerate, or create. `mockSendMutate` is
    // the mutation ChatView actually invokes; `mockCreate` is called directly by
    // ChatView. (`sendMessage`/`executeTurn` live behind the mocked
    // `useSendMessage`, so they are unreachable here by construction and are
    // deliberately NOT asserted as if they were evidence.)
    expect(mockSendMutate).not.toHaveBeenCalled();
    expect(mockCreate).not.toHaveBeenCalled();

    // A second arrival must not re-steal focus: the origin is read-once. Drive a
    // real effect re-run by switching conversations and back — navigating to the
    // identical URL changes no dependency, so the effect would not run at all and
    // the assertion would hold no matter what the implementation did.
    const newConversation = screen.getByRole("button", { name: "New conversation" });
    newConversation.focus();
    await router.navigate(`/scenarios/${SCENARIO}?conversation=${OLDER}`);
    await router.navigate(`/scenarios/${SCENARIO}?conversation=${NEWER}`);
    await waitFor(() => expect(router.state.location.search).toBe(`?conversation=${NEWER}`));
    expect(screen.getByRole("button", { name: /Evidence: demand demand-1/ })).not.toHaveFocus();
    expect(newConversation).toHaveFocus();
  });
  it("restores the conversation named in the URL rather than the newest one", () => {
    renderChat(`/scenarios/${SCENARIO}?conversation=${OLDER}`);

    // Returning to Chat must not silently move the planner to the newest
    // conversation — the next message would go somewhere they were not
    // reading (AC2).
    const selected = screen.getByRole("button", { current: "page" });
    expect(selected).toHaveTextContent(`Conversation ${OLDER.slice(0, 8)}`);
    // The second argument is the polling fallback's `refetchInterval`, `false`
    // while the event stream is healthy.
    expect(mockTimeline).toHaveBeenCalledWith(OLDER, false);
  });

  it("selects nothing until the planner chooses, and records the choice in the URL", async () => {
    const router = renderChat();

    expect(mockTimeline).toHaveBeenCalledWith("", false);
    await userEvent.click(
      screen.getByRole("button", { name: `Conversation ${OLDER.slice(0, 8)}` }),
    );

    await waitFor(() =>
      expect(router.state.location.search).toContain(`conversation=${OLDER}`),
    );
  });

  it("shows a restore skeleton instead of the empty prompt while the timeline loads", () => {
    mockTimeline.mockReturnValue({
      data: undefined,
      error: null,
      isError: false,
      isPending: true,
      refetch: vi.fn(),
    });

    renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    expect(screen.getByRole("status", { name: "Restoring conversation" })).toBeInTheDocument();
    // A conversation with persisted turns must never be described as having none.
    expect(
      screen.queryByText(/Start a new conversation about this scenario/),
    ).not.toBeInTheDocument();
  });

  it("offers no recovery link on a 404, where it would be a second dead end", () => {
    mockTimeline.mockReturnValue({
      data: undefined,
      error: { status: 404 },
      isError: true,
      isPending: false,
      refetch: vi.fn(),
    });

    renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    // Retry is already suppressed on a terminal status; the Scenario Data link
    // must be too. If this scenario's conversation is not visible, sending the
    // planner to that scenario's data offers a recovery path that is not one.
    expect(screen.getByRole("alert")).toHaveTextContent("Conversation not found");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: "Open Scenario Data" }),
    ).not.toBeInTheDocument();
  });

  it("surfaces a timeline failure as an alert, not as an empty conversation", () => {
    mockTimeline.mockReturnValue({
      data: undefined,
      error: { status: 503 },
      isError: true,
      isPending: false,
      refetch: vi.fn(),
    });

    renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this content.");
    expect(screen.getByRole("link", { name: "Open Scenario Data" })).toHaveAttribute(
      "href",
      `/scenarios/${SCENARIO}/data`,
    );
    expect(
      screen.queryByText(/Start a new conversation about this scenario/),
    ).not.toBeInTheDocument();
  });

  it("pins the version the planner is looking at when creating a conversation", async () => {
    mockCreate.mockResolvedValue(conversation(NEWER));
    renderChat();

    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));

    await waitFor(() =>
      expect(mockCreate).toHaveBeenCalledWith({
        scenario_id: SCENARIO,
        scenario_version_id: VERSION,
      }),
    );
  });

  it("surfaces a failed create instead of discarding the rejection", async () => {
    mockCreate.mockRejectedValue({ status: 503 });
    renderChat();

    await userEvent.click(screen.getByRole("button", { name: "New conversation" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent("Couldn't load this content."),
    );
    expect(screen.getByRole("link", { name: "Open Scenario Data" })).toHaveAttribute(
      "href",
      `/scenarios/${SCENARIO}/data`,
    );
  });

  it("keeps Scenario Data reachable when conversation loading fails", () => {
    mockConversations.mockReturnValue({
      data: undefined,
      error: { status: 503 },
      isError: true,
      isPending: false,
      refetch: vi.fn(),
    });

    renderChat();

    expect(screen.getByRole("link", { name: "Open Scenario Data" })).toHaveAttribute(
      "href",
      `/scenarios/${SCENARIO}/data`,
    );
  });

  it("keeps the accepted planner message visible beside a failed terminal turn", () => {
    const terminal = {
      ...activity("99999999-9999-9999-9999-999999999999", "unused", "2"),
      activity_type: "terminal_outcome" as const,
      outcome: {
        schema_version: "1",
        status: "failed" as const,
        reason: "provider_error" as const,
        detail: "The provider did not complete this turn.",
        next_step: "Try again.",
      },
    };
    mockTimeline.mockReturnValue({
      data: {
        conversation_id: NEWER,
        resource_version: 3,
        latest_agent_run_status: "agent_failed",
        items: [activity("11111111-1111-1111-1111-111111111111", "Check coverage", "1"), terminal],
        limit: 200,
        has_more: false,
      },
      error: null,
      isError: false,
      isPending: false,
      refetch: vi.fn(),
    });

    renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    expect(screen.getByText("Check coverage")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Provider failure" })).toBeInTheDocument();
  });

  it("reports the queued run literally and never as activity", () => {
    renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    expect(screen.getByText("Agent run accepted — queued")).toBeInTheDocument();
    expect(screen.queryByText(/Thinking/)).not.toBeInTheDocument();
    expect(screen.queryByText(/…$/)).not.toBeInTheDocument();
  });

  it("does not claim acceptance over a terminal run status", () => {
    mockTimeline.mockReturnValue({
      data: {
        conversation_id: NEWER,
        resource_version: 2,
        latest_agent_run_status: "agent_failed",
        items: [],
        limit: 200,
        has_more: false,
      },
      error: null,
      isError: false,
      isPending: false,
      refetch: vi.fn(),
    });

    renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    expect(screen.getByText("Agent run failed")).toBeInTheDocument();
    expect(screen.queryByText(/accepted/)).not.toBeInTheDocument();
  });

  it("says so when the timeline window is truncated", () => {
    mockTimeline.mockReturnValue({
      data: {
        conversation_id: NEWER,
        resource_version: 2,
        latest_agent_run_status: null,
        items: [activity("11111111-1111-1111-1111-111111111111", "Check coverage", "9")],
        limit: 200,
        has_more: true,
      },
      error: null,
      isError: false,
      isPending: false,
      refetch: vi.fn(),
    });

    renderChat(`/scenarios/${SCENARIO}?conversation=${NEWER}`);

    expect(screen.getByText(/Showing the most recent 200 activities/)).toBeInTheDocument();
  });

  it("does not emit a second h1 on a page that already has one", () => {
    renderChat();

    expect(screen.queryByRole("heading", { level: 1 })).not.toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 2, name: "Chat" })).toBeInTheDocument();
  });
});
