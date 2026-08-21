import { client } from "./client";
import type { paths } from "./schema";

type ScheduleRunStartPath = paths["/api/v1/schedule-runs"]["post"];

export type ScheduleRunStart =
  ScheduleRunStartPath["requestBody"]["content"]["application/json"];
export type ScheduleRunStarted =
  ScheduleRunStartPath["responses"][200]["content"]["application/json"];

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
