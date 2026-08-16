import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router";

import { createConversation } from "@/api/conversations";
import { InlineAlert } from "@/components/primitives/InlineAlert";
import { ReconnectBanner } from "@/components/primitives/ReconnectBanner";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { conversationsKey, useConversations } from "@/hooks/useConversations";
import { forgetOrigin, originElementId, peekOrigin, type EvidenceOrigin } from "@/features/evidence/origin";
import { useConversationStream } from "@/hooks/useConversationStream";
import { useScenarioContext } from "@/hooks/useScenarioContext";
import { useSendMessage } from "@/hooks/useSendMessage";
import { getErrorStatus, TERMINAL_STATUSES, USER_ERROR_COPY } from "@/lib/errors";
import { ActivityTimeline } from "./ActivityTimeline";
import { Composer } from "./Composer";
import { ConversationList } from "./ConversationList";

/** The CHECK constraint admits all seven AD-7 statuses, and this slice now
 * writes several of them: `agent_completed`, `agent_failed`, `agent_timed_out`
 * and `agent_cancelled` all reach a finished run. Rendering
 * "Agent run accepted — failed" would assert acceptance over a terminal
 * failure, so the accepted phrasing is scoped to the one status that means it.
 * Literal persisted state only: no typing indicator, no ellipsis, no ETA
 * (UX-DR5).
 *
 * Mapped explicitly rather than derived by stripping an `agent_` prefix:
 * `approval_required` carries no such prefix, so the strip was a no-op and the
 * planner was shown the raw wire value "Agent run approval_required". */
const RUN_STATUS_WORDS: Record<string, string> = {
  agent_queued: "accepted — queued",
  agent_running: "running",
  agent_completed: "completed",
  agent_failed: "failed",
  agent_timed_out: "timed out",
  agent_cancelled: "cancelled",
  approval_required: "waiting for approval",
};

function runStatusLabel(status: string): string {
  return `Agent run ${RUN_STATUS_WORDS[status] ?? status.replace(/_/g, " ")}`;
}

function ErrorState({
  error,
  onRetry,
  scenarioId,
}: Readonly<{ error: unknown; onRetry: () => void; scenarioId: string }>) {
  const status = getErrorStatus(error);
  const isTerminal = status !== undefined && TERMINAL_STATUSES.has(status);
  return (
    <InlineAlert
      action={
        <div className="flex flex-wrap items-center gap-3">
          {isTerminal ? null : (
            <Button className="min-h-11" onClick={onRetry} type="button" variant="outline">
              Retry
            </Button>
          )}
          {/* NOT COVERED: Runs and Results remain Epic 3 placeholder routes.
              Scenario Data is the only active recovery destination in this story.
              Suppressed on a 404 for the same reason Retry is: if the scenario
              or conversation is not visible, this link leads to a second dead
              end, which reads as a working recovery path and is not one. */}
          {isTerminal ? null : (
            <Link className="font-medium underline underline-offset-3" to={`/scenarios/${scenarioId}/data`}>
              Open Scenario Data
            </Link>
          )}
        </div>
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
  const navigate = useNavigate();
  const location = useLocation();
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
  const stream = useConversationStream(selectedId);
  const timeline = stream.timeline;

  // One restoration path, two entry points (Return to claim and browser Back).
  // History state survives Back/Forward but the Chat entry the planner lands on
  // may predate the jump, so sessionStorage mirrors it; either channel can be
  // the only one available (storage disabled, or a pre-jump history entry).
  const stateOrigin = (location.state as { evidenceOrigin?: EvidenceOrigin } | null)?.evidenceOrigin;
  const restored = useRef<string | null>(null);

  useEffect(() => {
    if (!selectedId || timeline.isPending || timeline.isError) return;
    const stored = peekOrigin();
    const origin = stored?.conversationId === selectedId
      ? stored
      : stateOrigin?.conversationId === selectedId ? stateOrigin : null;
    if (!origin) return;
    const elementId = originElementId(origin);
    if (restored.current === elementId) return;
    const node = document.getElementById(elementId);
    // Spend the token ONLY once the target is actually present. An errored,
    // empty, or window-truncated timeline renders no Evidence link, and
    // consuming there lost the restoration permanently with no retry.
    if (!node) return;
    if (stored === origin) forgetOrigin();
    restored.current = elementId;
    node.focus();
  }, [selectedId, stateOrigin, timeline.isError, timeline.isPending, stream.items]);

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
        <ErrorState error={start.error} onRetry={() => start.reset()} scenarioId={scenarioId} />
      ) : null}

      {conversations.isPending ? (
        <Skeleton aria-label="Loading conversations" className="h-11 w-full" role="status" />
      ) : conversations.isError ? (
        <ErrorState error={conversations.error} onRetry={() => void conversations.refetch()} scenarioId={scenarioId} />
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
            <ErrorState error={timeline.error} onRetry={() => void timeline.refetch()} scenarioId={scenarioId} />
          ) : (
            <>
              {/* Only rendered once something has actually gone wrong; a
                  healthy stream shows no banner at all. */}
              {stream.connection ? <ReconnectBanner state={stream.connection} /> : null}
              <ActivityTimeline items={stream.items} navigate={navigate} />
              {stream.updatesAreDelayed ? (
                // AC2 requires the fallback to be LABELLED. Silent polling
                // would leave the planner believing they are seeing live
                // activity when they are not.
                <p className="text-sm text-muted-foreground" role="status">
                  Live updates are unavailable. This conversation is refreshing on a
                  delay.
                </p>
              ) : null}
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
            scenarioId={scenarioId}
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
