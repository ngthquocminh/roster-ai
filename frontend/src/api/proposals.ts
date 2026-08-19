import { client } from "./client";
import type { components, paths } from "./schema";

type ProposalPath = paths["/api/v1/proposals/{proposal_id}"];
type RevisionPath = paths["/api/v1/proposals/{proposal_id}/revisions"];
type RejectionPath = paths["/api/v1/proposals/{proposal_id}/rejection"];

export type Proposal = ProposalPath["get"]["responses"][200]["content"]["application/json"];
export type ProposalRevision = RevisionPath["post"]["requestBody"]["content"]["application/json"];
export type ProposalRejection = RejectionPath["post"]["requestBody"]["content"]["application/json"];

/** The UNTRUSTED wire shape: identifiers and numbers, no labels or prose. */
export type ProposalConstraintInput = ProposalRevision["constraints"][number];

/** The TRUSTED shape the server composed and persisted, as rendered. */
export type ProposalConstraint = components["schemas"]["DraftConstraintV1"];

/**
 * Reduce a persisted constraint to the wire shape a revision may carry.
 *
 * The server recomposes `label`, `description` and `resolved_entities` from the
 * pinned projection, so sending them back would be both ignored and misleading.
 * Keeping the projection here means the card cannot accidentally round-trip a
 * description that no longer matches the number beside it.
 */
export function toConstraintInput(
  constraint: ProposalConstraint,
): ProposalConstraintInput {
  const entities = constraint.resolved_entities ?? [];
  const primary = entities[0];
  const related = entities[1];
  return {
    kind: constraint.kind,
    group: primary?.group ?? "work-areas-and-tasks",
    record_id: primary?.record_id ?? "",
    related_group: related?.group ?? null,
    related_record_id: related?.record_id ?? null,
    n: constraint.n ?? null,
    factor: constraint.factor ?? null,
    max_hours: constraint.max_hours ?? null,
    start_minute: constraint.start_minute ?? null,
    end_minute: constraint.end_minute ?? null,
    schema_version: constraint.schema_version ?? "1",
  };
}

export async function getProposal(proposalId: string): Promise<Proposal> {
  const { data, error, response } = await client.GET("/api/v1/proposals/{proposal_id}", {
    params: { path: { proposal_id: proposalId } },
  });
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function reviseProposal(
  proposalId: string,
  body: ProposalRevision,
  idempotencyKey: string,
): Promise<Proposal> {
  const { data, error, response } = await client.POST(
    "/api/v1/proposals/{proposal_id}/revisions",
    {
      params: {
        path: { proposal_id: proposalId },
        header: { "Idempotency-Key": idempotencyKey },
      },
      body,
    },
  );
  if (error) throw { ...error, status: response.status };
  return data;
}

export async function rejectProposal(
  proposalId: string,
  body: ProposalRejection,
  idempotencyKey: string,
): Promise<Proposal> {
  const { data, error, response } = await client.POST(
    "/api/v1/proposals/{proposal_id}/rejection",
    {
      params: {
        path: { proposal_id: proposalId },
        header: { "Idempotency-Key": idempotencyKey },
      },
      body,
    },
  );
  if (error) throw { ...error, status: response.status };
  return data;
}
