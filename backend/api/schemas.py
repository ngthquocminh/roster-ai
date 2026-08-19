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


class TerminalOutcomeActivityOut(ActivityCommonOut):
    activity_type: Literal["terminal_outcome"]
    outcome: TerminalOutcomeV1


ActivityItemOut = Annotated[
    PlannerMessageActivityOut
    | AgentResponseActivityOut
    | ClarificationActivityOut
    | DraftActivityOut
    | TerminalOutcomeActivityOut,
    Field(discriminator="activity_type"),
]


class AcceptedTurnOut(BaseModel):
    activity: ActivityItemOut
    resource_version: int
    agent_run_status: str
    sequence: str
    agent_run_id: UUID


class ExecutedTurnOut(BaseModel):
    activity: ActivityItemOut
    resource_version: int
    agent_run_status: str
    sequence: str
    agent_run_id: UUID


class TimelineOut(BaseModel):
    conversation_id: UUID
    resource_version: int
    latest_agent_run_status: str | None
    items: list[ActivityItemOut]
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
