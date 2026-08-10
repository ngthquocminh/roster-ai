import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router";

import { createConversation } from "@/api/conversations";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { conversationsKey, useConversations } from "@/hooks/useConversations";
import { useConversationTimeline } from "@/hooks/useConversationTimeline";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { useSendMessage } from "@/hooks/useSendMessage";
import { getErrorStatus, TERMINAL_STATUSES, USER_ERROR_COPY } from "@/lib/errors";
import { ActivityTimeline } from "./ActivityTimeline";
import { Composer } from "./Composer";
import { ConversationList } from "./ConversationList";

/** Only `agent_queued` is ever written in this slice, but the CHECK constraint
 * admits all seven AD-7 statuses and Epic 3 will write them. Rendering
 * "Agent run accepted — failed" would assert acceptance over a terminal
 * failure, so the accepted phrasing is scoped to the one status that means it.
 * Literal persisted state only: no typing indicator, no ellipsis, no ETA
 * (UX-DR5). */
function runStatusLabel(status: string): string {
  const bare = status.replace("agent_", "");
  return status === "agent_queued" ? `Agent run accepted — ${bare}` : `Agent run ${bare}`;
}

function ErrorState({ error, onRetry }: Readonly<{ error: unknown; onRetry: () => void }>) {
  const status = getErrorStatus(error);
  const isTerminal = status !== undefined && TERMINAL_STATUSES.has(status);
  return (
    <InlineAlert
      action={
        isTerminal ? undefined : (
          <Button className="min-h-11" onClick={onRetry} type="button" variant="outline">
            Retry
          </Button>
        )
      }
      description={
        isTerminal
          ? "The requested conversation is not available."
          : USER_ERROR_COPY.connection.description
      }
      title={isTerminal ? "Conversation not found" : USER_ERROR_COPY.connection.title}
      variant="destructive"
    />
  );
}

export function ChatView({ scenarioId }: Readonly<{ scenarioId: string }>) {
  const queryClient = useQueryClient();
  const context = useScenarioContext(scenarioId);
  const conversations = useConversations(scenarioId);
  // Selection lives in the URL, not component state: switching workspace tabs
  // unmounts this view, and `useState` would silently drop the planner back
  // onto the newest conversation — posting their next message into a different
  // conversation than the one they were reading (AC2).
  const [searchParams, setSearchParams] = useSearchParams();
  const requestedId = searchParams.get("conversation") ?? "";
  const items = conversations.data?.items ?? [];
  const selectedId = items.some((c) => c.id === requestedId) ? requestedId : "";
  const timeline = useConversationTimeline(selectedId);

  const select = (id: string) => {
    const next = new URLSearchParams(searchParams);
    next.set("conversation", id);
    setSearchParams(next, { replace: true });
  };

  const start = useMutation({
    // The pinned version comes from the context the planner is actually
    // looking at. The server validates it and never resolves "latest" — an
    // arbitrary initial pin would make AD-9's no-drift guarantee meaningless.
    mutationFn: () => {
      const version = context.data?.scenario_version_id;
      if (!version) throw new Error("scenario context is not loaded");
      return createConversation({
        scenario_id: scenarioId,
        scenario_version_id: version,
      });
    },
    onSuccess: async (created) => {
      select(created.id);
      await queryClient.invalidateQueries({ queryKey: conversationsKey(scenarioId) });
    },
  });

  const mutation = useSendMessage(selectedId, scenarioId);
  const pinned = items.find((c) => c.id === selectedId);

  return (
    <section aria-labelledby="chat-title" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* h2, not h1: the workspace shell already owns the page heading. */}
        <h2 className="text-lg font-medium" id="chat-title">
          Chat
        </h2>
        <Button
          className="min-h-11"
          disabled={start.isPending || !context.data}
          onClick={() => start.mutate()}
          type="button"
          variant="outline"
        >
          New conversation
        </Button>
      </div>

      {start.isError ? (
        <ErrorState error={start.error} onRetry={() => start.reset()} />
      ) : null}

      {conversations.isPending ? (
        <Skeleton aria-label="Loading conversations" className="h-11 w-full" role="status" />
      ) : conversations.isError ? (
        <ErrorState error={conversations.error} onRetry={() => void conversations.refetch()} />
      ) : (
        <ConversationList
          conversations={items}
          onSelect={select}
          selectedId={selectedId}
        />
      )}

      {selectedId ? (
        <div className="space-y-4">
          {pinned ? (
            <p className="font-mono text-xs text-muted-foreground">
              Pinned scenario version {pinned.scenario_version_id}
            </p>
          ) : null}
          {timeline.isPending ? (
            <div aria-label="Restoring conversation" className="space-y-2" role="status">
              {[0, 1, 2].map((row) => (
                <Skeleton className="h-16 w-full" key={row} />
              ))}
            </div>
          ) : timeline.isError ? (
            <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} />
          ) : (
            <>
              <ActivityTimeline items={timeline.data.items} />
              {timeline.data.has_more ? (
                <p className="text-xs text-muted-foreground">
                  Showing the most recent {timeline.data.limit} activities. Earlier
                  activity is not displayed.
                </p>
              ) : null}
              {timeline.data.latest_agent_run_status ? (
                <p className="text-sm text-muted-foreground">
                  {runStatusLabel(timeline.data.latest_agent_run_status)}
                </p>
              ) : null}
            </>
          )}
          <Composer
            isPending={mutation.isPending}
            onSend={(text) => mutation.mutateAsync({ text })}
          />
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Start a new conversation about this scenario—for example, ask about coverage,
          demand, or constraints.
        </p>
      )}
    </section>
  );
}
