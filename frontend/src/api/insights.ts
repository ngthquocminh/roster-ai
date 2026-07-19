/**
 * Thin typed wrapper for GET /runs/{run_id}/insights (RES-04/RES-05).
 * InsightOut is already generated in schema.d.ts (unlike results.ts's
 * RunResult — no hand-written type needed here). Same pattern as
 * constraints.ts / runs.ts: request/response shapes come from the generated
 * `paths` type via the single `client` instance.
 *
 * getRunInsights does NOT interpret the `ready` field — it returns the raw
 * InsightOut body as-is so the caller (InsightPanel, plan 04-06) branches on
 * `ready`, never on HTTP status code. `ready: false` is a deliberate `200`,
 * not an error condition, per docs/API.md and PROJECT.md's "v0.4 key
 * context" #2.
 */
import { client } from "./client";

export async function getRunInsights(runId: string) {
  const { data, error, response } = await client.GET("/runs/{run_id}/insights", {
    params: { path: { run_id: runId } },
  });
  if (error) {
    // RES-05: 502 (provider failure / grounding-guard rejection) must be
    // distinguishable — attach status, same T-1-02 convention.
    throw { status: response.status, ...error };
  }
  return data; // InsightOut: { ready, run_id, report?, status?, reason? }
}
