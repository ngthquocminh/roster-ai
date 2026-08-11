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
vi.mock("@/api/conversations", () => ({ createConversation: vi.fn() }));

import { createConversation } from "@/api/conversations";
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
  mockConversations.mockReset();
  mockTimeline.mockReset();
  mockContext.mockReset();
  mockSend.mockReset();
  mockCreate.mockReset();
  mockContext.mockReturnValue({ data: { scenario_version_id: VERSION } });
  mockSend.mockReturnValue({ isPending: false, mutateAsync: vi.fn() });
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
  it("restores the conversation named in the URL rather than the newest one", () => {
    renderChat(`/scenarios/${SCENARIO}?conversation=${OLDER}`);

    // Returning to Chat must not silently move the planner to the newest
    // conversation — the next message would go somewhere they were not
    // reading (AC2).
    const selected = screen.getByRole("button", { current: "page" });
    expect(selected).toHaveTextContent(`Conversation ${OLDER.slice(0, 8)}`);
    expect(mockTimeline).toHaveBeenCalledWith(OLDER);
  });

  it("selects nothing until the planner chooses, and records the choice in the URL", async () => {
    const router = renderChat();

    expect(mockTimeline).toHaveBeenCalledWith("");
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
