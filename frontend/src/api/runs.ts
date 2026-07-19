/**
 * Thin typed wrappers for the run endpoints this app's UI calls (RUN-01
 * trigger, RUN-02/RUN-04 list-poll, plus Phase 4's getRun single-run fetch).
 * Same pattern as scenarios.ts / constraints.ts: request/response shapes
 * come from the generated `paths` type (`./schema.d.ts`) via the single
 * `client` instance — no hand-authored interface or type alias for a
 * payload lives here.
 *
 * getRun(runId) — added in Phase 4 for D-12's deep-link status probe: the
 * Results route fetches RunOut first (always succeeds regardless of run
 * status) and branches on it before ever calling GET /runs/{run_id}/result,
 * which 409s before COMPLETED.
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

export async function getRun(runId: string) {
  const { data, error, response } = await client.GET("/runs/{run_id}", {
    params: { path: { run_id: runId } },
  });
  if (error) {
    throw { status: response.status, ...error };
  }
  return data; // RunOut — always succeeds regardless of run status (D-12)
}
