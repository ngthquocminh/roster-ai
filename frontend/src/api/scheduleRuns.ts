import { client } from "./client";
import type { paths } from "./schema";

type ScheduleRunStartPath = paths["/api/v1/schedule-runs"]["post"];
type ScheduleRunListPath = paths["/api/v1/schedule-runs"]["get"];
type ScheduleRunCancellationPath =
  paths["/api/v1/schedule-runs/{run_id}/cancellation"]["post"];

export type ScheduleRunStart =
  ScheduleRunStartPath["requestBody"]["content"]["application/json"];
export type ScheduleRunStarted =
  ScheduleRunStartPath["responses"][200]["content"]["application/json"];
export type ScheduleRunListQuery = ScheduleRunListPath["parameters"]["query"];
export type ScheduleRunPage =
  ScheduleRunListPath["responses"][200]["content"]["application/json"];
export type ScheduleRunSummary = ScheduleRunPage["items"][number];
export type ScheduleRunCancellation =
  ScheduleRunCancellationPath["requestBody"]["content"]["application/json"];
export type ScheduleRunCancelled =
  ScheduleRunCancellationPath["responses"][200]["content"]["application/json"];

export async function startScheduleRun(
  body: ScheduleRunStart,
  idempotencyKey: string,
): Promise<ScheduleRunStarted> {
  const { data, error, response } = await client.POST("/api/v1/schedule-runs", {
    params: { header: { "Idempotency-Key": idempotencyKey } },
    body,
  });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function listScheduleRuns(
  params: ScheduleRunListQuery,
): Promise<ScheduleRunPage> {
  const { data, error, response } = await client.GET("/api/v1/schedule-runs", {
    params: { query: params },
  });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function cancelScheduleRun(
  runId: string,
  body: ScheduleRunCancellation,
  idempotencyKey: string,
): Promise<ScheduleRunCancelled> {
  const { data, error, response } = await client.POST(
    "/api/v1/schedule-runs/{run_id}/cancellation",
    {
      params: {
        path: { run_id: runId },
        header: { "Idempotency-Key": idempotencyKey },
      },
      body,
    },
  );
  if (error) throw { ...error, status: response.status };
  return data;
}
