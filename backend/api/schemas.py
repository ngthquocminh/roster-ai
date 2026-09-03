"""Pydantic request/response models for the API."""
from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator
from application.contracts.grounding import GroundedResponseV1
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.proposal import (
    DraftConstraintProposalV1,
    DraftConstraintV1,
    ResolvedEntityV1,
)
from application.contracts.scenario_projection import LockV1
from application.contracts.audit_envelope import AuditOutcomeV1, WorkerFactsV1
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.schedule_version import MetricSetV1, ScheduleRunStatusV1


class ScenarioCreate(BaseModel):
    name: str = Field(min_length=1)
    fixture: str = Field(min_length=1)
    time_limit_s: float = Field(default=60.0, gt=0)


class ScenarioOut(BaseModel):
    id: str
    name: str
    fixture: str
    time_limit_s: float
    created_at: str


class RunOut(BaseModel):
    id: str
    scenario_id: str
    status: str
    created_at: str
    started_at: Optional[str] = None
    finished_at: Optional[str] = None
    solver_status: Optional[str] = None
    error: Optional[str] = None


class InsightOut(BaseModel):
    ready: bool
    run_id: str
    report: Optional[str] = None    # present when ready=True (INS-01)
    status: Optional[str] = None    # present when ready=False (D-07)
    reason: Optional[str] = None    # present when ready=False (D-07)

    @model_validator(mode="after")
    def check_ready_fields(self) -> "InsightOut":
        if self.ready and self.report is None:
            raise ValueError("report must be set when ready=True")
        if not self.ready and self.status is None:
            raise ValueError("status must be set when ready=False")
        return self


class ConstraintParseRequest(BaseModel):
    scenario_id: str = Field(min_length=1)
    text: str = Field(min_length=1, max_length=2000)


class AppliedConstraint(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str


class RejectedConstraint(BaseModel):
    tool: str
    error: str


class ConstraintParseResponse(BaseModel):
    applied: list[AppliedConstraint]
    rejected: list[RejectedConstraint]
    clarification_needed: str | None
    no_constraint_found: bool


class OverrideOut(BaseModel):
    id: str
    tool: str
    args: dict
    parsed_constraint: str | None = None  # None for pre-D-02 legacy entries


class ProblemDetailsV1(BaseModel):
    type: str
    title: str
    status: int
    detail: str
    code: str
    # AD-13 requires stale/expired/conflict problems to carry literal
    # expected/current context. Declaring it here is what publishes it into
    # `openapi.json` and the generated client types -- without these two the
    # frontend reads the fields through an unchecked cast.
    expected: dict | None = None
    current: dict | None = None


class ConversationCreateIn(BaseModel):
    scenario_id: UUID
    # The version the planner is actually looking at, taken from the scenario
    # context they were served. Both fields are selectors to be validated
    # server-side against the session's site — never authority (AD-2/AD-15).
    # The server does NOT resolve "latest": an arbitrary initial pin makes
    # AD-9's no-drift guarantee meaningless.
    scenario_version_id: UUID


class MessageCreateIn(BaseModel):
    # Strip before length validation so whitespace-only text is rejected as a
    # 422 by the request model rather than reaching the use case and escaping
    # as an uncaught ValueError -> 500.
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20_000)]


class ConversationOut(BaseModel):
    id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    resource_version: int


class ConversationListOut(BaseModel):
    items: list[ConversationOut]
    limit: int
    has_more: bool


class ActivityCommonOut(BaseModel):
    schema_version: str
    activity_id: UUID
    conversation_id: UUID
    conversation_resource_version: int
    scenario_id: UUID
    scenario_version_id: UUID
    occurred_at: datetime
    # A JSON *string*, on reads as well as writes. AD-21's SSE id is
    # `<stream_uuid>:<sequence>`; a JSON number becomes an IEEE-754 double in
    # the browser, so a timeline that omitted this or emitted it as a number
    # would leave Story 2.4 with no lossless resume point.
    sequence: str


class PlannerMessageActivityOut(ActivityCommonOut):
    activity_type: Literal["planner_message"]
    message_id: UUID
    text: str


class AgentResponseActivityOut(ActivityCommonOut):
    activity_type: Literal["agent_response"]
    response: GroundedResponseV1


class ClarificationActivityOut(ActivityCommonOut):
    activity_type: Literal["clarification"]
    clarification: ResolvedClarificationV1


class DraftActivityOut(ActivityCommonOut):
    activity_type: Literal["draft"]
    proposal_id: UUID
    proposal_version_id: UUID
    consequence_summary: str


class ApprovalRequestActivityOut(ActivityCommonOut):
    activity_type: Literal["approval_request"]
    approval_id: UUID
    approval_state: Literal["pending", "consumed", "rejected", "expired", "stale"]
    agent_run_id: UUID | None
    schedule_run_id: UUID
    candidate_schedule_version_id: UUID
    baseline_schedule_version: str | None
    consequence_summary: str
    parameter_hash: str
    consequence_hash: str
    policy_version: str
    expires_at: datetime


class RunProgressActivityOut(BaseModel):
    schema_version: str
    activity_id: UUID
    activity_type: Literal["run_progress"]
    schedule_run_id: UUID
    status: Literal[
        "solver_queued",
        "solver_running",
        "cancellation_requested",
        "solver_completed",
        "solver_infeasible",
        "solver_timed_out",
        "solver_cancelled",
        "solver_failed",
    ]
    reason: str | None
    resource_version: int
    occurred_at: datetime
    sequence: str


class TerminalOutcomeActivityOut(ActivityCommonOut):
    activity_type: Literal["terminal_outcome"]
    outcome: TerminalOutcomeV1


class ApprovalRequestIn(BaseModel):
    schedule_run_id: UUID
    expected_resource_version: int = Field(ge=1)
    # No default (Decision 3): an explicit `null` asserts "expects absence"
    # (EAD-2) and is a meaningful, distinct value from a caller who omitted
    # the key altogether. `= None` here would silently conflate the two.
    expected_baseline_schedule_version: str | None = Field(...)


class ApprovalDecisionIn(BaseModel):
    decision: Literal["approve", "reject"]
    expected_resource_version: int = Field(ge=1)


class ApprovalOut(BaseModel):
    approval_id: UUID
    state: Literal["pending", "consumed", "rejected", "expired", "stale"]
    schedule_run_id: UUID
    candidate_schedule_version_id: UUID
    baseline_schedule_version: str | None
    scenario_version_id: UUID
    consequence_summary: str
    policy_version: str
    # `agent_run_id` serves AC2 ("the same agent-run and approval identifiers
    # remain visible"); `created_at` is the review surface's "requested at".
    # `parameter_hash`/`consequence_hash` are deliberately NOT published here:
    # AC1 asks for the material parameters themselves -- which the card already
    # renders as the run, candidate and baseline versions -- not for the digest
    # sealing them. Provenance (Story 4.4) reads the hashes from `audit_event`,
    # which carries both, so nothing needs them on this read model.
    agent_run_id: UUID | None
    created_at: datetime
    expires_at: datetime
    resource_version: int


class ApprovalListOut(BaseModel):
    items: list[ApprovalOut]


class ProvenanceCommonOut(BaseModel):
    occurred_at: datetime
    item_type: str
    site_id: UUID
    actor_id: UUID | None
    initiated_by_actor_id: UUID | None
    decided_by_actor_id: UUID | None
    request_id: UUID | None
    attempt_id: UUID | None
    conversation_id: UUID | None
    agent_run_id: UUID | None
    tool_call_id: str | None
    approval_id: UUID | None
    job_attempt_id: UUID | None
    schedule_run_id: UUID | None
    audit_id: UUID | None
    schedule_version_id: UUID | None
    scenario_version_id: UUID | None
    evidence_refs: tuple[EvidenceRefV1, ...]
    schema_version: str


class SolverRunProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["solver_run"]
    status: ScheduleRunStatusV1
    reason: str | None
    baseline_schedule_version: str | None
    candidate_schedule_version_id: UUID | None
    comparison_status: Literal["available", "unavailable"]
    comparison_reason: str | None
    metrics: MetricSetV1 | None


class RunProgressProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["run_progress"]
    status: ScheduleRunStatusV1
    reason: str | None
    resource_version: int


class DraftProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["draft"]
    proposal_id: UUID
    proposal_version_id: UUID
    consequence_summary: str


class EvidenceClaimProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["evidence_claim"]
    claim: str
    value: float | int | str | None
    unit: str | None


class ToolProposalProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["tool_proposal"]
    tool_name: str


class ApprovalRequestProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["approval_request"]
    state: Literal["pending", "consumed", "rejected", "expired", "stale"]
    consequence_summary: str
    parameter_hash: str
    consequence_hash: str
    policy_version: str
    expires_at: datetime


class ApprovalDecisionProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["approval_decision"]
    outcome: AuditOutcomeV1
    state: Literal["consumed", "rejected", "expired", "stale"]


class AuditRecordProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["audit_record"]
    action: str
    outcome: AuditOutcomeV1
    success: bool
    safe_summary: str
    parameter_hash: str
    consequence_hash: str
    policy_version: str
    app_version: str
    worker_facts: WorkerFactsV1


class BaselinePromotionProvenanceOut(ProvenanceCommonOut):
    item_type: Literal["baseline_promotion"]
    before_version: str | None
    after_version: str


DecisionProvenanceItemOut = Annotated[
    SolverRunProvenanceOut | RunProgressProvenanceOut | DraftProvenanceOut
    | EvidenceClaimProvenanceOut | ToolProposalProvenanceOut
    | ApprovalRequestProvenanceOut | ApprovalDecisionProvenanceOut
    | AuditRecordProvenanceOut | BaselinePromotionProvenanceOut,
    Field(discriminator="item_type"),
]


class DecisionProvenanceOut(BaseModel):
    schedule_run_id: UUID
    site_id: UUID
    items: list[DecisionProvenanceItemOut]
    schema_version: str


ConversationActivityItemOut = Annotated[
    PlannerMessageActivityOut
    | AgentResponseActivityOut
    | ClarificationActivityOut
    | DraftActivityOut
    | ApprovalRequestActivityOut
    | TerminalOutcomeActivityOut,
    Field(discriminator="activity_type"),
]


ActivityItemOut = Annotated[
    PlannerMessageActivityOut
    | AgentResponseActivityOut
    | ClarificationActivityOut
    | DraftActivityOut
    | ApprovalRequestActivityOut
    | RunProgressActivityOut
    | TerminalOutcomeActivityOut,
    Field(discriminator="activity_type"),
]


class AcceptedTurnOut(BaseModel):
    activity: ConversationActivityItemOut
    resource_version: int
    agent_run_status: str
    sequence: str
    agent_run_id: UUID


class ExecutedTurnOut(BaseModel):
    activity: ConversationActivityItemOut
    resource_version: int
    agent_run_status: str
    sequence: str
    agent_run_id: UUID


class TimelineOut(BaseModel):
    conversation_id: UUID
    resource_version: int
    latest_agent_run_status: str | None
    latest_agent_run_status_reason: str | None
    items: list[ConversationActivityItemOut]
    limit: int
    # The window is anchored at the newest events; `has_more` reports that
    # older ones exist beyond it. Without it a full page is indistinguishable
    # from an exactly-`limit`-length stream.
    has_more: bool


class ProposalRevisionIn(BaseModel):
    # The UNTRUSTED shape, deliberately. `DraftConstraintV1` is the trusted,
    # resolved contract; binding it to a request body would let a client post
    # its own `resolved_entities`, `label` and `description` straight into an
    # immutable proposal version. The application re-resolves every identifier
    # and recomposes every description through
    # `application/drafting/resolve.py` — the same path the model-facing
    # capability uses. The upper bound is enforced in the use case against
    # `scheduling_draft_max_constraints`; the generous cap here only stops an
    # unbounded body from being parsed at all.
    constraints: list[DraftConstraintProposalV1] = Field(min_length=1, max_length=100)
    expected_resource_version: int = Field(ge=1)


class ProposalRejectionIn(BaseModel):
    expected_resource_version: int = Field(ge=1)


class ScheduleRunCancellationIn(BaseModel):
    expected_resource_version: int = Field(ge=1)


class ScheduleRunStartIn(BaseModel):
    proposal_id: UUID
    expected_resource_version: int = Field(ge=1)


#: AD-7's closed status graph. Named once so the list route's summary and the
#: command routes' `ScheduleRunOut` cannot silently diverge on the vocabulary.
ScheduleRunStatusOut = Literal[
    "solver_queued",
    "solver_running",
    "cancellation_requested",
    "solver_completed",
    "solver_infeasible",
    "solver_timed_out",
    "solver_cancelled",
    "solver_failed",
]


class ScheduleRunOut(BaseModel):
    schedule_run_id: UUID
    status: ScheduleRunStatusOut
    reason: str | None
    resource_version: int
    cancellation_requested: bool
    # The cancellation command's replay payload intentionally contains only
    # semantic command state. Story 3.7's read surface will populate the
    # aggregate timestamps; keeping them optional avoids manufacturing them.
    created_at: datetime | None = None
    finished_at: datetime | None = None


class EvidenceRefOut(BaseModel):
    scenario_version_id: UUID
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    producing_run_version: str | None
    baseline_schedule_version: str | None
    group: str
    record_id: str
    field: str | None = None
    start_minute: int | None = None
    end_minute: int | None = None
    schema_version: str = "1"


class MetricSetOut(BaseModel):
    interval_coverage_required_minutes: list[tuple[str, float]] = []
    interval_coverage_served_minutes: list[tuple[str, float]] = []
    function_coverage_required_minutes: list[tuple[str, float]] = []
    function_coverage_served_minutes: list[tuple[str, float]] = []
    overtime_minutes: float = 0.0
    total_cost: float = 0.0
    objective_components: list[tuple[str, float]] = []
    assignment_count: int = 0
    member_count: int = 0
    schema_version: str = "1"


class ConstraintResultOut(BaseModel):
    constraint_id: str
    constraint_type: str
    constraint_class: Literal["hard", "soft"]
    satisfied: bool
    measured_value: float | None
    limit: float | None
    unit: str
    contributing_assignment_ids: list[str]
    contributing_evidence_refs: list[EvidenceRefOut]
    schema_version: str = "1"


class ScheduleVersionOut(BaseModel):
    schedule_version_id: UUID
    schedule_run_id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    proposal_id: UUID
    proposal_version_id: UUID
    feasible_solver_status: Literal["OPTIMAL", "FEASIBLE"]
    assignments: list["AssignmentOut"]
    metrics: MetricSetOut
    constraint_results: list[ConstraintResultOut]
    warnings: list[str]
    evidence_refs: list[EvidenceRefOut]
    created_at: datetime | None
    schema_version: str = "1"


class AssignmentDiffOut(BaseModel):
    added_worker_ids: list[str]
    removed_worker_ids: list[str]
    added_shift_ids: list[str]
    removed_shift_ids: list[str]
    added_task_ids: list[str]
    removed_task_ids: list[str]
    schema_version: str = "1"


class ComparisonOut(BaseModel):
    candidate_schedule_version_id: UUID
    candidate_schedule_run_id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    expected_baseline_schedule_version: str | None
    current_baseline_schedule_version: str | None
    stale: bool
    assignment_diff: AssignmentDiffOut | None
    candidate_metrics: MetricSetOut
    baseline_metrics: MetricSetOut | None
    candidate_constraint_results: list[ConstraintResultOut]
    baseline_hard_constraint_results: list[ConstraintResultOut]
    warnings: list[str]
    unresolved_gap_record_ids: list[str]
    evidence_refs: list[EvidenceRefOut]
    schema_version: str = "1"


class ScheduleRunResultOut(BaseModel):
    """A completed run's result. The comparison is a PART, not the whole.

    EAD-8 makes the baseline comparison refusable (an unreadable baseline
    assignment supply must never render as "the baseline is empty"), but that
    refusal is scoped to the comparison alone: the run, the candidate schedule,
    and any pending approval on it remain readable and actionable. Expressing a
    sub-computation's refusal as a whole-resource failure would take the
    schedule, the evidence, and the approval controls down with it.
    """

    run: ScheduleRunOut
    candidate: ScheduleVersionOut | None
    comparison: ComparisonOut | None
    #: Literal, planner-facing reason the comparison is absent for a run that is
    #: otherwise complete. `None` whenever `comparison` is present, or whenever
    #: the run simply has not produced one yet.
    comparison_unavailable_reason: str | None = None
    #: The LIVE site baseline pointer. Normally read off the comparison; carried
    #: here so a refused comparison still leaves a well-formed approval request
    #: possible (it is the binding's `expected_baseline_schedule_version`).
    current_baseline_schedule_version: str | None = None


class ScheduleRunSummaryOut(BaseModel):
    """One row of the Runs workspace list (Story 3.7 AC1)."""

    schedule_run_id: UUID
    status: ScheduleRunStatusOut
    reason: str | None
    resource_version: int
    created_at: datetime
    # AC1's "updated time": newest `persisted_event.occurred_at` on the run's
    # stream, falling back to `created_at`. Not `finished_at`, which is NULL
    # for exactly the non-terminal runs a planner monitors.
    updated_at: datetime
    finished_at: datetime | None
    scenario_version_id: UUID
    proposal_id: UUID
    proposal_version: int
    # Story 3.1 Decision 7: stays None until Epic 4 supplies a real baseline
    # pointer. Rendered as "—" client-side, never as "" or 0 (Trap 4).
    baseline_schedule_version: str | None


class ScheduleRunPageOut(BaseModel):
    #: Mirrors the subset of the API's established page envelope
    #: (`TaskPageOut` and siblings) that this route can honour. `group` is a
    #: scenario-projection concept and does not apply; `schema_version` is a
    #: versioned-contract commitment Story 3.7 does not own and is deliberately
    #: not claimed here.
    scenario_id: UUID
    items: list[ScheduleRunSummaryOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class ProposalOut(BaseModel):
    proposal_id: UUID
    proposal_version_id: UUID
    scenario_id: UUID
    scenario_version_id: UUID
    current_scenario_version_id: UUID
    expected_baseline_schedule_version: str | None
    resolved_entities: list[ResolvedEntityV1]
    constraints: list[DraftConstraintV1]
    preserved_locks: list[LockV1]
    consequence_summary: str
    canonical_hash: str
    canonical_hash_algorithm: str
    canonical_hash_schema_version: str
    state: Literal["active", "rejected"]
    resource_version: int
    stale: bool
    schema_version: str


class AuthSessionOut(BaseModel):
    app_user_id: UUID
    site_id: UUID
    csrf_token: str
    expires_at: datetime


class FixtureCatalogueEntryOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    fixture_id: str
    scenario_name: str
    scenario_version_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    imported_at: datetime
    site_id: UUID


class ScenarioContextOut(BaseModel):
    schema_version: str = "v1"
    scenario_name: str
    scenario_id: UUID
    # Exposed so a client that pins a version (AD-9) can select by identity
    # instead of asking the server to re-derive "latest" under a second,
    # divergent rule. See ConversationCreateIn.
    scenario_version_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    site_id: UUID
    baseline_schedule_version: str | None


class ScenarioOverviewOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    fixture_id: str
    scenario_name: str
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    horizon_start: datetime
    site_timezone: str
    horizon_minutes: int
    baseline_schedule_version: str | None
    projection_generated_at: datetime
    work_area_count: int
    task_count: int
    worker_count: int
    demand_interval_count: int
    baseline_assignment_count: int
    lock_count: int
    constraint_count: int


class TaskProjectionOut(BaseModel):
    record_id: str
    task_id: str
    name: str
    function: str
    area_id: str
    area_name: str
    unit_type_id: str | None


class QualificationRefOut(BaseModel):
    task_id: str
    rate: float


class AvailabilityWindowOut(BaseModel):
    kind: Literal["roster", "availability"]
    start_minute: int
    end_minute: int


class WorkerProjectionOut(BaseModel):
    record_id: str
    contact_id: str
    name: str
    employment_type: str
    grade: str
    eba: str
    contracted_hours: float
    qualifications: list[QualificationRefOut]
    availability_windows: list[AvailabilityWindowOut]


class DemandIntervalOut(BaseModel):
    record_id: str
    family: Literal["outbound", "inbound", "indirect"]
    task_id: str
    area_id: str | None
    start_minute: int
    end_minute: int
    amount: float
    unit: Literal["volume", "headcount"]


class AssignmentOut(BaseModel):
    record_id: str
    worker_id: str
    task_id: str
    shift_id: str | None
    start_minute: int
    end_minute: int


class LockOut(BaseModel):
    record_id: str
    target_type: str
    target_ref: str
    scope: str
    source: str


class ConstraintProjectionOut(BaseModel):
    record_id: str
    constraint_type: str
    value: str
    value_type: str | None


class TaskPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["work-areas-and-tasks"]
    items: list[TaskProjectionOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class WorkerPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["workers"]
    items: list[WorkerProjectionOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class DemandIntervalPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["demand"]
    items: list[DemandIntervalOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class AssignmentPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["baseline-assignments"]
    items: list[AssignmentOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class LockPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["locks"]
    items: list[LockOut]
    next_cursor: int | None
    total_count: int
    matching_count: int


class ConstraintPageOut(BaseModel):
    schema_version: str = "v1"
    scenario_id: UUID
    scenario_version_id: UUID
    site_id: UUID
    group: Literal["constraints-and-objectives"]
    items: list[ConstraintProjectionOut]
    next_cursor: int | None
    total_count: int
    matching_count: int
