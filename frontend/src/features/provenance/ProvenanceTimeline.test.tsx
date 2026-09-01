import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router";
import { expect, it } from "vitest";

import type { RunProvenance } from "@/api/provenance";
import { ProvenanceTimeline } from "./ProvenanceTimeline";

const scenarioId = "11111111-1111-4111-8111-111111111111";
const runId = "22222222-2222-4222-8222-222222222222";
const versionId = "33333333-3333-4333-8333-333333333333";
const common = {
  occurred_at: "2026-08-31T01:00:00Z", site_id: "site-1", actor_id: null,
  initiated_by_actor_id: null, decided_by_actor_id: null, request_id: null,
  attempt_id: null, conversation_id: "conversation-1", agent_run_id: null,
  tool_call_id: null, approval_id: null, job_attempt_id: null,
  schedule_run_id: runId, audit_id: null, schedule_version_id: null,
  scenario_version_id: versionId, evidence_refs: [], schema_version: "v1",
};

it("renders an ordered, literal, inspectable timeline without leaking planted payload text", async () => {
  const marker = "PRIVATE_TOOL_ARGUMENT_MARKER";
  const provenance = {
    schedule_run_id: runId, site_id: "site-1", schema_version: "v1",
    items: [
      { ...common, item_type: "tool_proposal", tool_call_id: "tool-call-1", tool_name: "solve_schedule", pending_payload: marker },
      { ...common, item_type: "approval_decision", approval_id: "approval-1", outcome: "approval_rejected", state: "rejected" },
      { ...common, item_type: "evidence_claim", claim: "Persisted coverage", value: 42, unit: "minutes", evidence_refs: [{ scenario_version_id: versionId, checksum_algorithm: "sha256", checksum_schema_version: "rfc8785-v1", checksum_digest: "a".repeat(64), producing_run_version: null, baseline_schedule_version: null, group: "demand", record_id: "demand-1", field: "amount", start_minute: 0, end_minute: 60, schema_version: "v1" }] },
      { ...common, item_type: "baseline_promotion", before_version: "baseline-before", after_version: "baseline-after" },
    ],
  } as unknown as RunProvenance;

  render(<MemoryRouter><ProvenanceTimeline provenance={provenance} scenarioId={scenarioId} /></MemoryRouter>);

  expect(screen.getByRole("list", { name: "Decision provenance" })).toBeInTheDocument();
  expect(screen.getByText("Tool proposed: solve_schedule")).toBeInTheDocument();
  expect(screen.getByText("Approval decision: approval_rejected")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy tool call identifier tool-call-1" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /Evidence: demand demand-1, amount, 0–60 minutes/ })).toBeInTheDocument();
  expect(screen.getByText("Before")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy promoted baseline version baseline-after" })).toBeInTheDocument();
  expect(screen.queryByText(marker)).not.toBeInTheDocument();

  const details = screen.getByRole("button", { name: "Details" });
  expect(details).toHaveAttribute("aria-expanded", "false");
  await userEvent.click(details);
  expect(details).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByText("Persisted value")).toBeInTheDocument();
});
