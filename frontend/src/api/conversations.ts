import { client } from "./client";
import type { paths } from "./schema";

type Root = paths["/api/v1/conversations"];
type Message = paths["/api/v1/conversations/{conversation_id}/messages"];
export type ConversationPage = Root["get"]["responses"][200]["content"]["application/json"];
export type Conversation = ConversationPage["items"][number];
export type ConversationCreate = Root["post"]["requestBody"]["content"]["application/json"];
export type MessageCreate = Message["post"]["requestBody"]["content"]["application/json"];
export type AcceptedTurn = Message["post"]["responses"][201]["content"]["application/json"];
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
