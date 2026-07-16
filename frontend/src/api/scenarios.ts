/**
 * Thin typed wrappers for the three endpoints this phase's UI calls
 * (SCEN-01, SCEN-02). Every request/response shape comes from the generated
 * `paths` type (`./schema.d.ts`) via the single `client` instance — no
 * hand-authored interface or type alias for an endpoint payload lives here.
 * See COVERAGE.md: the eight other endpoints are typed already but
 * deliberately un-wrapped this phase.
 *
 * Kept thin by design: business/UI logic belongs in the hooks (plans 01-06,
 * 01-07), not here.
 */
import { client } from "./client";

export async function listScenarios() {
  const { data, error } = await client.GET("/scenarios");
  if (error) throw error;
  return data;
}

export async function listFixtures() {
  const { data, error } = await client.GET("/fixtures");
  if (error) throw error;
  return data;
}

export async function createScenario(body: { name: string; fixture: string }) {
  const { data, error, response } = await client.POST("/scenarios", { body });
  if (error) {
    // T-1-02: attach the HTTP status so callers can *branch* (400 unknown
    // fixture vs 422 validation — UI-SPEC gives these two distinct inline
    // messages) without needing to *display* anything the backend said.
    throw { status: response.status, ...error };
  }
  return data;
}
