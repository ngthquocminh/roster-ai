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
import type { paths } from "./schema";

// Derived (not hand-authored) via indexed access into the generated `paths`
// type — see 01-04-PLAN.md: "Deriving a parameter type from the generated
// types (e.g. via an indexed access into paths) is fine and encouraged;
// declaring the field list by hand is not." `time_limit_s` is made optional
// here because openapi-typescript types every property carrying a JSON
// Schema `default` as non-optional (a codegen-tool artifact, not an API
// contract fact) — the real `ScenarioCreate` schema's own `required` array
// omits it, matching docs/API.md's documented `time_limit_s` default of 60,
// and SCEN-02's UI never collects it.
type CreateScenarioBody = paths["/scenarios"]["post"]["requestBody"]["content"]["application/json"];

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

export async function createScenario(
  body: Omit<CreateScenarioBody, "time_limit_s"> & Partial<Pick<CreateScenarioBody, "time_limit_s">>,
) {
  const { data, error, response } = await client.POST("/scenarios", {
    body: { time_limit_s: 60, ...body },
  });
  if (error) {
    // T-1-02: attach the HTTP status so callers can *branch* (400 unknown
    // fixture vs 422 validation — UI-SPEC gives these two distinct inline
    // messages) without needing to *display* anything the backend said.
    throw { status: response.status, ...error };
  }
  return data;
}
