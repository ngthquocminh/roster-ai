import { client } from "./client";
import type { paths } from "./schema";
import { API_BASE_URL } from "../lib/env";

type Root = paths["/api/v1/conversations"];
type Message = paths["/api/v1/conversations/{conversation_id}/messages"];
type Execute = paths["/api/v1/conversations/{conversation_id}/agent-runs/{agent_run_id}/execute"];
export type ConversationPage = Root["get"]["responses"][200]["content"]["application/json"];
export type Conversation = ConversationPage["items"][number];
export type ConversationCreate = Root["post"]["requestBody"]["content"]["application/json"];
export type MessageCreate = Message["post"]["requestBody"]["content"]["application/json"];
export type AcceptedTurn = Message["post"]["responses"][201]["content"]["application/json"];
export type ExecutedTurn = Execute["post"]["responses"][200]["content"]["application/json"];
export type Timeline = paths["/api/v1/conversations/{conversation_id}/timeline"]["get"]["responses"][200]["content"]["application/json"];

export async function listConversations(scenarioId: string): Promise<ConversationPage> {
  const { data, error, response } = await client.GET("/api/v1/conversations", { params: { query: { scenario_id: scenarioId } } });
  if (error) throw { ...error, status: response.status };
  return data;
}
export async function createConversation(body: ConversationCreate): Promise<Conversation> {
  const { data, error, response } = await client.POST("/api/v1/conversations", { body });
  if (error) throw { ...error, status: response.status };
  return data;
}
export async function getConversationTimeline(conversationId: string): Promise<Timeline> {
  const { data, error, response } = await client.GET("/api/v1/conversations/{conversation_id}/timeline", { params: { path: { conversation_id: conversationId } } });
  if (error) throw { ...error, status: response.status };
  return data;
}
export async function sendMessage(conversationId: string, body: MessageCreate): Promise<AcceptedTurn> {
  const { data, error, response } = await client.POST("/api/v1/conversations/{conversation_id}/messages", { params: { path: { conversation_id: conversationId } }, body });
  if (error) throw { ...error, status: response.status };
  return data;
}
export async function executeTurn(conversationId: string, agentRunId: string): Promise<ExecutedTurn> {
  const { data, error, response } = await client.POST(
    "/api/v1/conversations/{conversation_id}/agent-runs/{agent_run_id}/execute",
    { params: { path: { conversation_id: conversationId, agent_run_id: agentRunId } } },
  );
  if (error) throw { ...error, status: response.status };
  return data;
}

/**
 * The one endpoint this app does **not** call through `client.ts`.
 *
 * `openapi-fetch` returns parsed bodies and cannot consume a stream, so the SSE
 * endpoint needs a bare URL for `EventSource`. The rule `client.ts`'s docstring
 * actually protects is *one module knows the base URL* — that still holds:
 * `API_BASE_URL` is imported from `lib/env` here exactly as it is there, and no
 * component or hook reads `import.meta.env`.
 *
 * The cursor is composed here rather than by the caller so AD-21's
 * `<stream_uuid>:<sequence>` format has one definition on this side of the wire.
 * `sequence` stays a **string** end to end: the column is `Numeric(38, 0)` and a
 * JavaScript number would silently lose precision past 2^53 and poison the
 * resume point. Omitting it means "replay everything", which is also what a
 * sequence of `0` means.
 *
 * `withCredentials` is deliberately left at its default. `API_BASE_URL` is the
 * SPA's own origin (`frontend/.env.example`; Vite proxies `/api` in both
 * `server` and `preview`), so the `__Host-` session cookie rides along
 * same-origin. Setting `withCredentials: true` would only matter cross-origin,
 * where it fails anyway — the API leaves `allow_credentials` at `False` under
 * D-02. **A cross-origin `VITE_API_BASE_URL` breaks this feature.**
 */
export function conversationEventsUrl(conversationId: string, sequence?: string | null): string {
  const base = `${API_BASE_URL.replace(/\/+$/, "")}/api/v1/conversations/${encodeURIComponent(conversationId)}/events`;
  if (!sequence) return base;
  return `${base}?${new URLSearchParams({ last_event_id: `${conversationId}:${sequence}` })}`;
}
