/** Thin generated-contract wrappers for immutable scenario catalogue reads. */
import { client } from "./client";
import type { paths } from "./schema";


export type FixtureCatalogueEntry =
  paths["/api/v1/scenarios"]["get"]["responses"][200]["content"]["application/json"][number];

export type ScenarioContext =
  paths["/api/v1/scenarios/{scenario_id}"]["get"]["responses"][200]["content"]["application/json"];

export async function listFixtureVersions(): Promise<
  FixtureCatalogueEntry[]
> {
  const { data, error, response } = await client.GET("/api/v1/scenarios");
  if (error) {
    // Transport status last: ProblemDetailsV1 carries its own `status`, and a
    // gateway-rewritten body must never decide the sign-in redirect.
    throw { ...error, status: response.status };
  }
  // A 200 with no body would otherwise resolve undefined, which TanStack
  // reports as a query error — a success rendered as a connection failure.
  return data ?? [];
}

export async function getScenarioContext(
  scenarioId: string,
): Promise<ScenarioContext> {
  const { data, error, response } = await client.GET(
    "/api/v1/scenarios/{scenario_id}",
    { params: { path: { scenario_id: scenarioId } } },
  );
  if (error) {
    throw { ...error, status: response.status };
  }
  return data;
}
