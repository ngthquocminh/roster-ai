import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";

import { PRIMITIVE_FIXTURES, type PrimitiveFixture } from "@/components/primitives/fixtures";
import { ComparisonSummary } from "@/components/run-results/ComparisonSummary";
import { TerminalOutcomeCard } from "@/components/run-results/TerminalOutcomeCard";
import { ProgressCard } from "@/components/runs/ProgressCard";
import { RunsTable } from "@/components/runs/RunsTable";
import { ApprovalDecisionPanel } from "@/features/approvals/ApprovalDecisionPanel";
import { ApprovalRequestCard } from "@/features/approvals/ApprovalRequestCard";
import { ActivityTimeline } from "@/features/chat/ActivityTimeline";
import { DraftCard } from "@/features/chat/DraftCard";
import { ProvenanceTimeline } from "@/features/provenance/ProvenanceTimeline";
import { approvalKey } from "@/hooks/useApproval";
import { proposalKey } from "@/hooks/useProposal";

export type StateFamily =
  | "message" | "draft" | "run" | "comparison" | "approval"
  | "terminal-outcome" | "alert" | "skeleton" | "empty-state" | "provenance";

export type StateFixture = Readonly<{
  family: StateFamily;
  state: string;
  render: () => ReactNode;
}>;

/**
 * Exhaustive over `PrimitiveFixture["primitive"]` on purpose: the parameter is the
 * union, not `string`, so adding a primitive to `PRIMITIVE_FIXTURES` without filing
 * it here is a TypeScript error rather than a silent fall-through into `provenance`.
 * Family assignment decides what each state is compared against — distinctness is
 * pairwise WITHIN a family — so a mis-filed primitive quietly changes the proof.
 */
const primitiveFamily = (primitive: PrimitiveFixture["primitive"]): StateFamily => {
  switch (primitive) {
    case "StatusBadge":
      return "run";
    case "InlineAlert":
    case "ReconnectBanner":
      return "alert";
    case "Skeleton":
      return "skeleton";
    case "EmptyState":
      return "empty-state";
    case "EvidenceLink":
    case "EvidenceHighlight":
    case "IdentifierCopyButton":
      return "provenance";
  }
};

const primitiveStates: readonly StateFixture[] = PRIMITIVE_FIXTURES.map((fixture) => ({
  family: primitiveFamily(fixture.primitive),
  state: fixture.state,
  render: fixture.render,
}));

// ---------------------------------------------------------------------------
// Feature states. Every entry below renders the SHIPPED component.
//
// No entry wraps itself in a generated `aria-label`, and none echoes its own state
// name into the markup. An earlier form did both, which made the distinctness
// assertion a theorem rather than a test: a separate guard already asserts
// family/state identities are unique, so a label derived from the state name was
// unique by construction. Verified at code review by mutation — two states
// differing only by `text-red-600`/`text-green-600` passed, and three UX-DR32
// prohibitions on DraftCard's real root passed.
//
// Providers live inside each entry's own `render`, per Task 3. Query-backed
// components are driven by seeding the cache through the hooks' own exported key
// factories rather than by mocking the hooks, so this stays a plain module that
// the consuming test imports without `vi.mock`.
// ---------------------------------------------------------------------------

const SCENARIO_ID = "33333333-3333-4333-8333-333333333333";
const VERSION_ID = "44444444-4444-4444-8444-444444444444";
const APPROVAL_ID = "11111111-1111-1111-1111-111111111111";
const PROPOSAL_ID = "11111111-1111-4111-8111-111111111111";
const RUN_ID = "22222222-2222-4222-8222-222222222222";

function seeded(entries: ReadonlyArray<readonly [readonly unknown[], unknown]>, node: ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  for (const [key, value] of entries) client.setQueryData(key, value);
  return <QueryClientProvider client={client}><MemoryRouter>{node}</MemoryRouter></QueryClientProvider>;
}

const timeline = (items: readonly unknown[]) => (
  <MemoryRouter><ActivityTimeline items={items as never} navigate={() => {}} /></MemoryRouter>
);

const activity = {
  schema_version: "1", conversation_id: "22222222-2222-2222-2222-222222222222",
  conversation_resource_version: 2, scenario_id: SCENARIO_ID, scenario_version_id: VERSION_ID,
  occurred_at: "2026-08-10T00:00:00Z",
};

const plannerMessage = {
  ...activity, activity_id: "11111111-1111-1111-1111-111111111111",
  activity_type: "planner_message", message_id: "55555555-5555-5555-5555-555555555555",
  text: "Compare the saved schedule.", sequence: "1",
};

// docs/DOMAIN-MODEL.md §1/§3: `required_headcount_minutes` is answerable in MINUTES
// only for `indirect`, because `headcount` is the one demand unit that already is a
// rate. Trap 10 forbids copying `apiStubs.ts`'s impossible
// `required_headcount_minutes` + `family: outbound` pairing into a new fixture, so
// this claim uses the one pairing the domain model permits for a minutes answer.
const groundedResponse = {
  ...activity, activity_id: "88888888-8888-8888-8888-888888888888",
  activity_type: "agent_response", sequence: "2",
  response: {
    schema_version: "1", scenario_version_id: VERSION_ID,
    segments: [
      { schema_version: "1", kind: "prose", text: "Indirect cover required is" },
      {
        schema_version: "1", kind: "claim", metric: "required_headcount_minutes",
        arguments: { schema_version: "1", task_id: "pick", family: "indirect", start_minute: 780, end_minute: 1020 },
        result_id: "result-1", value: 720, unit: "minutes", verdict: "supported", failure: null,
        evidence_refs: [{
          schema_version: "1", scenario_version_id: VERSION_ID, checksum_algorithm: "sha256",
          checksum_schema_version: "1", checksum_digest: "a".repeat(64), producing_run_version: null,
          baseline_schedule_version: null, group: "demand", record_id: "DEM-204", field: "amount",
          start_minute: 780, end_minute: 1020,
        }],
      },
    ],
  },
};

const clarification = {
  ...activity, activity_id: "99999999-9999-9999-9999-999999999999",
  activity_type: "clarification", sequence: "3",
  clarification: {
    schema_version: "1", question: "Which worker did you mean?", scenario_version_id: VERSION_ID,
    dropped_candidate_count: 1,
    candidates: [{ schema_version: "1", group: "workers", record_id: "w1", label: "Alex (CONTACT-9)", scenario_version_id: VERSION_ID }],
  },
};

// `detail` is held IDENTICAL across every reason on purpose, mirroring
// ActivityTimeline.test.tsx: if the fixture varied the detail string it would
// supply the distinctness itself, and the assertion would pass even if the
// component collapsed every reason to one label.
const TERMINAL_REASONS = [
  "refused", "provider_error", "invalid_output", "budget_exhausted",
  "deadline_exceeded", "capability_error", "approval_not_grantable",
] as const;

const terminalActivity = (reason: string, index: number) => ({
  ...activity, activity_id: `aaaaaaaa-aaaa-4aaa-8aaa-${String(index).padStart(12, "0")}`,
  activity_type: "terminal_outcome", sequence: String(index + 4),
  outcome: {
    schema_version: "1", status: reason === "refused" ? "completed" : "failed", reason,
    detail: "the same detail for every reason", next_step: "Review Scenario Data.",
  },
});

const entity = { group: "workers" as const, record_id: "w1", label: "Alex (CONTACT-9)", scenario_version_id: VERSION_ID, schema_version: "1" };
const proposal = (overrides: Record<string, unknown> = {}) => ({
  proposal_id: PROPOSAL_ID, proposal_version_id: "22222222-2222-4222-8222-222222222222",
  scenario_id: SCENARIO_ID, scenario_version_id: VERSION_ID, current_scenario_version_id: VERSION_ID,
  expected_baseline_schedule_version: "baseline-v1", resolved_entities: [entity],
  constraints: [{ kind: "set_max_hours", resolved_entities: [entity], max_hours: 40, description: "Cap Alex (CONTACT-9) at 40 hours per week.", schema_version: "1" }],
  preserved_locks: [{ record_id: "lock-1", target_type: "worker", target_ref: "w1", scope: "assignment", source: "fixture", schema_version: "1" }],
  consequence_summary: "One reversible constraint; preserved one existing lock; no baseline change.",
  canonical_hash: "a".repeat(64), canonical_hash_algorithm: "sha256",
  canonical_hash_schema_version: "rfc8785-v1", state: "active", resource_version: 1,
  stale: false, schema_version: "1", ...overrides,
});

const approval = (state: string, overrides: Record<string, unknown> = {}) => ({
  approval_id: APPROVAL_ID, state, schedule_run_id: RUN_ID,
  candidate_schedule_version_id: "33333333-3333-3333-3333-333333333333",
  baseline_schedule_version: null, scenario_version_id: VERSION_ID,
  consequence_summary: "Candidate replaces no current baseline.", policy_version: "policy-v1",
  agent_run_id: null, created_at: "2026-08-29T00:00:00Z", expires_at: "2099-08-29T01:00:00Z",
  resource_version: 1, ...overrides,
});

const scheduleRun = (status: string, reason: string | null = null) => ({
  schedule_run_id: RUN_ID, status, reason, resource_version: 1,
  created_at: "2026-08-22T10:00:00Z", updated_at: "2026-08-22T10:03:00Z", finished_at: null,
  scenario_version_id: VERSION_ID, proposal_id: PROPOSAL_ID, proposal_version: 1,
  baseline_schedule_version: null,
});

const metrics = {
  interval_coverage_required_minutes: [["demand-1", 60]],
  interval_coverage_served_minutes: [["demand-1", 45]],
  function_coverage_required_minutes: [["Picking", 60]],
  function_coverage_served_minutes: [["Picking", 45]],
  overtime_minutes: 10, total_cost: 125, objective_components: [["unmet_minutes", 15]],
  assignment_count: 1, member_count: 1, schema_version: "1",
};

const comparison = (overrides: Record<string, unknown> = {}) => ({
  candidate_schedule_version_id: "11111111-1111-1111-1111-111111111111",
  candidate_schedule_run_id: RUN_ID, scenario_id: SCENARIO_ID, scenario_version_id: VERSION_ID,
  expected_baseline_schedule_version: "baseline-v1", current_baseline_schedule_version: "baseline-v1",
  stale: false,
  assignment_diff: { added_worker_ids: ["worker-1"], removed_worker_ids: ["worker-2"], added_shift_ids: ["shift-1"], removed_shift_ids: [], added_task_ids: ["task-1"], removed_task_ids: [], schema_version: "1" },
  candidate_metrics: metrics,
  baseline_metrics: { ...metrics, interval_coverage_served_minutes: [], overtime_minutes: 0, total_cost: 100, objective_components: [["unmet_minutes", 60]], assignment_count: 0, member_count: 0 },
  candidate_constraint_results: [{ constraint_id: "hard:q", constraint_type: "qualification", constraint_class: "hard", satisfied: true, measured_value: 0, limit: 0, unit: "assignments", contributing_assignment_ids: [], contributing_evidence_refs: [], schema_version: "1" }],
  baseline_hard_constraint_results: [], warnings: ["Review overtime"],
  unresolved_gap_record_ids: ["demand-1"], evidence_refs: [], schema_version: "1", ...overrides,
});

const provenanceCommon = {
  occurred_at: "2026-08-31T01:00:00Z", site_id: "site-1", actor_id: null, initiated_by_actor_id: null,
  decided_by_actor_id: null, request_id: null, attempt_id: null, conversation_id: "conversation-1",
  agent_run_id: null, tool_call_id: null, approval_id: null, job_attempt_id: null,
  schedule_run_id: RUN_ID, audit_id: null, schedule_version_id: null,
  scenario_version_id: VERSION_ID, evidence_refs: [], schema_version: "v1",
};

const provenanceOf = (items: readonly unknown[]) => (
  <MemoryRouter>
    <ProvenanceTimeline
      provenance={{ schedule_run_id: RUN_ID, site_id: "site-1", schema_version: "v1", items } as never}
      scenarioId={SCENARIO_ID}
    />
  </MemoryRouter>
);

const evidenceRef = {
  scenario_version_id: VERSION_ID, checksum_algorithm: "sha256", checksum_schema_version: "rfc8785-v1",
  checksum_digest: "a".repeat(64), producing_run_version: null, baseline_schedule_version: null,
  group: "demand", record_id: "demand-1", field: "amount", start_minute: 0, end_minute: 60, schema_version: "v1",
};

const customStates: readonly StateFixture[] = [
  { family: "message", state: "planner message", render: () => timeline([plannerMessage]) },
  { family: "message", state: "grounded agent response", render: () => timeline([groundedResponse]) },
  { family: "message", state: "clarification", render: () => timeline([clarification]) },
  ...TERMINAL_REASONS.map((reason, index): StateFixture => ({
    family: "message", state: `terminal ${reason.replace(/_/g, " ")}`,
    render: () => timeline([terminalActivity(reason, index)]),
  })),

  { family: "draft", state: "fresh", render: () => seeded([[proposalKey(PROPOSAL_ID), proposal()]], <DraftCard proposalId={PROPOSAL_ID} />) },
  { family: "draft", state: "stale", render: () => seeded([[proposalKey(PROPOSAL_ID), proposal({ stale: true })]], <DraftCard proposalId={PROPOSAL_ID} />) },
  { family: "draft", state: "rejected", render: () => seeded([[proposalKey(PROPOSAL_ID), proposal({ state: "rejected" })]], <DraftCard proposalId={PROPOSAL_ID} />) },

  // Named `progress …` because `PRIMITIVE_FIXTURES`' StatusBadge already owns
  // `run/queued` and `run/running`; identities must stay unique within the family.
  { family: "run", state: "progress queued", render: () => <ProgressCard run={scheduleRun("solver_queued") as never} /> },
  { family: "run", state: "progress running", render: () => <ProgressCard run={scheduleRun("solver_running") as never} /> },
  { family: "run", state: "progress cancellation requested", render: () => <ProgressCard run={scheduleRun("cancellation_requested") as never} /> },

  {
    family: "comparison", state: "populated",
    render: () => <ComparisonSummary approvalsUnavailable={false} comparison={comparison() as never} onRequestApproval={() => {}} pendingApproval={false} requestError={false} requestPending={false} />,
  },
  {
    // Task 3's "'Not computed' for an absent metric". `delta()` returns that
    // literal when either side is null, which is what the solver produces when it
    // hits its time limit before proving cost-optimality — a real absent metric,
    // not a zero. Rendered through the component so the copy is the component's.
    family: "comparison", state: "not computed",
    render: () => <ComparisonSummary approvalsUnavailable={false} comparison={comparison({ baseline_metrics: { ...metrics, total_cost: null, overtime_minutes: null } }) as never} onRequestApproval={() => {}} pendingApproval={false} requestError={false} requestPending={false} />,
  },
  {
    family: "comparison", state: "stale binding",
    render: () => <ComparisonSummary approvalsUnavailable={false} comparison={comparison({ stale: true, current_baseline_schedule_version: "baseline-v2" }) as never} onRequestApproval={() => {}} pendingApproval={false} requestError={false} requestPending={false} />,
  },

  { family: "approval", state: "pending", render: () => seeded([[approvalKey(APPROVAL_ID), approval("pending")]], <ApprovalDecisionPanel approvalId={APPROVAL_ID} />) },
  { family: "approval", state: "rejected", render: () => seeded([[approvalKey(APPROVAL_ID), approval("rejected")]], <ApprovalDecisionPanel approvalId={APPROVAL_ID} />) },
  { family: "approval", state: "expired", render: () => seeded([[approvalKey(APPROVAL_ID), approval("expired")]], <ApprovalDecisionPanel approvalId={APPROVAL_ID} />) },
  { family: "approval", state: "consumed", render: () => seeded([[approvalKey(APPROVAL_ID), approval("consumed")]], <ApprovalDecisionPanel approvalId={APPROVAL_ID} />) },
  { family: "approval", state: "request pending", render: () => <ApprovalRequestCard approval={approval("pending", { expires_at: "2026-08-27T12:00:00Z" }) as never} now={new Date("2026-08-27T11:00:00Z")} /> },
  // EAD-7: "pending, overdue" is one PRESENTED state, not a fourth stored one —
  // the same stored `pending` row read after its expiry instant.
  { family: "approval", state: "pending-overdue", render: () => <ApprovalRequestCard approval={approval("pending", { expires_at: "2026-08-27T12:00:00Z" }) as never} now={new Date("2026-08-27T13:00:00Z")} /> },

  { family: "terminal-outcome", state: "infeasible", render: () => <TerminalOutcomeCard run={scheduleRun("solver_infeasible", "no_feasible_schedule") as never} /> },
  { family: "terminal-outcome", state: "timed out", render: () => <TerminalOutcomeCard run={scheduleRun("solver_timed_out", "wall_time_exhausted") as never} /> },
  { family: "terminal-outcome", state: "cancelled", render: () => <TerminalOutcomeCard run={scheduleRun("solver_cancelled", "cancelled_by_planner") as never} /> },
  { family: "terminal-outcome", state: "failed", render: () => <TerminalOutcomeCard run={scheduleRun("solver_failed", "budget_exhausted") as never} /> },

  { family: "empty-state", state: "intrinsically empty", render: () => timeline([]) },
  {
    family: "empty-state", state: "filtered empty",
    render: () => seeded([], <RunsTable emptyExplanation="No runs match the current filters." error={null} isLoading={false} runs={[]} scenarioId={SCENARIO_ID} />),
  },

  { family: "provenance", state: "collapsed item", render: () => provenanceOf([{ ...provenanceCommon, item_type: "tool_proposal", tool_call_id: "tool-call-1", tool_name: "solve_schedule" }]) },
  { family: "provenance", state: "expanded item with evidence", render: () => provenanceOf([{ ...provenanceCommon, item_type: "evidence_claim", claim: "Persisted coverage", value: 42, unit: "minutes", evidence_refs: [evidenceRef] }]) },
  { family: "provenance", state: "expanded item without evidence", render: () => provenanceOf([{ ...provenanceCommon, item_type: "evidence_claim", claim: "Persisted coverage", value: 42, unit: "minutes", evidence_refs: [] }]) },
];

export const STATE_MATRIX: readonly StateFixture[] = [...primitiveStates, ...customStates];
