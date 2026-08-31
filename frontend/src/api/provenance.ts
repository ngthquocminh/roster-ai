import { client } from "./client";
import type { paths } from "./schema";

type ProvenancePath = paths["/api/v1/approvals/provenance"]["get"];

export type RunProvenance = ProvenancePath["responses"][200]["content"]["application/json"];
export type ProvenanceItem = RunProvenance["items"][number];

export async function getRunProvenance(scheduleRunId: string): Promise<RunProvenance> {
  const { data, error, response } = await client.GET("/api/v1/approvals/provenance", {
    params: { query: { schedule_run_id: scheduleRunId } },
  });
  if (error) throw { ...error, status: response.status };
  // openapi-fetch widens JSON arrays nested inside MetricSetV1, while the
  // generated response contract preserves those entries as tuples.
  return data as RunProvenance;
}
