/**
 * Thin typed wrapper for POST /constraints (CONS-01/CONS-05). Same pattern
 * as scenarios.ts: request/response types derived via indexed access into
 * the generated `paths` type — no hand-authored payload interface.
 */
import { client } from "./client";
import type { paths } from "./schema";

type ConstraintParseRequest =
  paths["/constraints"]["post"]["requestBody"]["content"]["application/json"];

export async function applyConstraint(body: ConstraintParseRequest) {
  const { data, error, response } = await client.POST("/constraints", { body });
  if (error) {
    // CONS-05 needs response.status to distinguish 503 (provider down) from
    // 422 (validation) — same T-1-02 convention as createScenario.
    throw { status: response.status, ...error };
  }
  return data; // ConstraintParseResponse: applied[], rejected[], clarification_needed, no_constraint_found
}
