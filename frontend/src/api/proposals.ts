import { client } from "./client";
import type { paths } from "./schema";

type ProposalPath = paths["/api/v1/proposals/{proposal_id}"];
type RevisionPath = paths["/api/v1/proposals/{proposal_id}/revisions"];
type RejectionPath = paths["/api/v1/proposals/{proposal_id}/rejection"];

export type Proposal = ProposalPath["get"]["responses"][200]["content"]["application/json"];
export type ProposalRevision = RevisionPath["post"]["requestBody"]["content"]["application/json"];
export type ProposalRejection = RejectionPath["post"]["requestBody"]["content"]["application/json"];
export type ProposalConstraint = ProposalRevision["constraints"][number];

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
  idempotencyKey = crypto.randomUUID(),
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
  idempotencyKey = crypto.randomUUID(),
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
