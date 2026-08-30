import { client } from "./client";
import type { paths } from "./schema";

type CreatePath = paths["/api/v1/approvals"]["post"];
type ListPath = paths["/api/v1/approvals"]["get"];
type GetPath = paths["/api/v1/approvals/{approval_id}"]["get"];
type DecisionPath = paths["/api/v1/approvals/{approval_id}/decision"]["post"];

export type ApprovalRequest = CreatePath["requestBody"]["content"]["application/json"];
export type Approval = CreatePath["responses"][200]["content"]["application/json"];
export type ApprovalList = ListPath["responses"][200]["content"]["application/json"];
export type ApprovalDecision = DecisionPath["requestBody"]["content"]["application/json"];

export async function requestApproval(body: ApprovalRequest, idempotencyKey: string): Promise<Approval> {
  const { data, error, response } = await client.POST("/api/v1/approvals", {
    params: { header: { "Idempotency-Key": idempotencyKey } }, body,
  });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function listRunApprovals(scheduleRunId: string): Promise<ApprovalList> {
  const { data, error, response } = await client.GET("/api/v1/approvals", {
    params: { query: { schedule_run_id: scheduleRunId } },
  });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function getApproval(approvalId: string): Promise<GetPath["responses"][200]["content"]["application/json"]> {
  const { data, error, response } = await client.GET("/api/v1/approvals/{approval_id}", { params: { path: { approval_id: approvalId } } });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function decideApproval(approvalId: string, body: ApprovalDecision, idempotencyKey: string): Promise<Approval> {
  const { data, error, response } = await client.POST("/api/v1/approvals/{approval_id}/decision", { params: { path: { approval_id: approvalId }, header: { "Idempotency-Key": idempotencyKey } }, body });
  if (error) throw { ...error, status: response.status };
  return data;
}
