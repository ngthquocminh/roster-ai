/**
 * Thin typed wrappers for the two run endpoints this phase's UI calls
 * (RUN-01 trigger, RUN-02/RUN-04 list-poll). Same pattern as scenarios.ts /
 * constraints.ts: request/response shapes come from the generated `paths`
 * type (`./schema.d.ts`) via the single `client` instance — no hand-authored
 * interface or type alias for a payload lives here.
 *
 * No getRun/per-run wrapper: this phase polls only the list endpoint
 * (UI-SPEC Data strategy); the run-detail route lands on the Phase-4
 * ResultsPlaceholder.
 */
import { client } from "./client";

export async function listRuns(scenarioId: string) {
  const { data, error, response } = await client.GET("/scenarios/{scenario_id}/runs", {
    params: { path: { scenario_id: scenarioId } },
  });
  if (error) {
    // T-1-02: attach the HTTP status so callers can branch on it.
    throw { status: response.status, ...error };
  }
  return data;
}

export async function triggerRun(scenarioId: string) {
  const { data, error, response } = await client.POST("/scenarios/{scenario_id}/runs", {
    params: { path: { scenario_id: scenarioId } },
  });
  if (error) {
    // T-1-02: needed for E1's 404 ("scenario no longer exists") branch.
    throw { status: response.status, ...error };
  }
  return data;
}
