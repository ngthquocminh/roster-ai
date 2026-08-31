"""Request, inspect, and decide exact baseline-approval bindings."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import Connection, select
from sqlalchemy.exc import IntegrityError

from api.deps import AgentRuntimeFactory, CapabilityComposer, PostCommitActions, SiteContextOpener, get_agent_runtime_factory, get_approval_repository, get_audit_writer, get_capability_registry, get_clock, get_conversation_repository, get_membership_reader, get_post_commit_actions, get_projection_reader, get_proposal_repository, get_schedule_run_repository, get_session, get_settings, get_site_baseline_reader, get_site_baseline_writer, get_site_context, get_site_context_opener
from api.problems import problem_response
from api.schemas import ApprovalDecisionIn, ApprovalListOut, ApprovalOut, ApprovalRequestIn, ProblemDetailsV1
from application.capabilities.installed import enabled_feature_policy
from application.ports.approval import ApprovalRepository, AuditWriter
from application.ports.conversation import AgentRunNotQueuedError, ConversationRepository
from application.ports.conversation import ClaimedAgentRunV1
from application.ports.schedule_run import ScheduleRunRepository
from application.ports.session import ResolvedSession
from application.ports.site_baseline import SiteBaselineReader, SiteBaselineWriter
from application.ports.membership import MembershipReader
from application.ports.proposal import ProposalRepository
from application.ports.scenario_projection import ScenarioProjectionReader
from application.use_cases.request_approval import ApprovalRequestError, RequestApprovalCommandV1, request_approval
from application.use_cases.decide_approval import DecideApprovalCommandV1, DecideApprovalError, PostWriteApprovalNotPendingError, decide_approval
from application.use_cases.promote_baseline import BaselineConcurrentlyMovedError
from application.contracts.canonical import contract_digest
from application.contracts.audit_envelope import AuditEnvelopeV1, WorkerFactsV1
from application.contracts.agent_runtime import AgentApprovalDecisionV1, AgentBudgetV1
from application.contracts.grounding import GroundedAnswerV1
from application.capabilities.deps import AgentDepsV1
from application.capabilities.registry import CapabilityGrantContextV1, PLANNER_ROLE, POLICY_GENERATION
from application.use_cases.execute_turn import activity_payload, execute_turn, failed_outcome_for_exception, terminal_status
from application.use_cases.finalize_agent_run import finalize_agent_run
from adapters.postgres.short_transaction_projection import ShortTransactionScenarioProjectionReader
from adapters.postgres.schema import conversation, membership
from settings import Settings

router = APIRouter(prefix="/approvals", tags=["approvals"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=40)]
_RESPONSES = {403: {"model": ProblemDetailsV1}, 404: {"model": ProblemDetailsV1}, 409: {"model": ProblemDetailsV1}, 422: {"model": ProblemDetailsV1}}
_DECISION_RESPONSES = _RESPONSES

#: Status per stable problem code (AD-13). `approval_not_granted` is 403 at BOTH
#: sites -- the router's feature-policy pre-check and the use case's own
#: `ApprovalNotGrantedError` describe the identical condition, and Task 8 fixes
#: it at 403, so mapping the second one to 422 published two statuses for one
#: state.
_ERROR_STATUS = {
    "candidate_not_found": 404,
    "approval_not_granted": 403,
    "approval_already_pending": 409,
    "candidate_not_promotable": 409,
    "stale_resource_version": 409,
    "stale_baseline_version": 409,
    "approval_not_found": 404,
    "approval_not_pending": 409,
    "agent_run_not_cancellable": 409,
}

#: Detail per decision-route problem code. `approval_not_granted` is a policy
#: refusal, not a stale binding.
_DECISION_DETAIL = {
    "approval_not_granted": "Current policy does not grant baseline approval.",
    "approval_not_found": "No approval is visible in this site.",
    "approval_not_pending": "The approval already reached a terminal state.",
    "stale_resource_version": "The approval changed since the version you pinned.",
    "agent_run_not_cancellable": "The agent run awaiting this approval is no longer in a cancellable state.",
}
_DECISION_DETAIL_FALLBACK = "The approval is no longer valid for this decision."


def _context(expected: dict, current: dict) -> dict | None:
    """AD-13's literal expected/current context, omitted when there is none.

    `DecideApprovalError` defaults both to `{}`, and an always-present `{}` is
    not "no context" to a JSON client -- it is an empty object, which is truthy
    in JavaScript and rendered `Expected: {}` on the decision panel.
    """
    if not expected and not current:
        return None
    return {"expected": expected, "current": current}


def _out(binding, now: datetime) -> ApprovalOut:
    # EAD-7: a read that observes `now() >= expires_at` PRESENTS the binding as
    # expired and writes nothing. The terminal `expired` state materialises only
    # inside a decision-attempt transaction, which Story 4.2 owns.
    state = "expired" if binding.state == "pending" and binding.expires_at <= now else binding.state
    return ApprovalOut(approval_id=binding.approval_id, state=state, schedule_run_id=binding.schedule_run_id, candidate_schedule_version_id=binding.candidate_schedule_version_id, baseline_schedule_version=binding.baseline_schedule_version, scenario_version_id=binding.scenario_version_id, consequence_summary=binding.consequence_summary, policy_version=binding.policy_version, agent_run_id=binding.agent_run_id, created_at=binding.created_at, expires_at=binding.expires_at, resource_version=binding.resource_version)


def _drive_resumed_turn(*, resume, binding, settings, runtime_factory, compose_capabilities,
                        projection_reader, conversations, proposals, open_site_context) -> None:
    """Drive one already-resumed run after TX2 has committed."""
    with open_site_context(binding.site_id) as connection:
        context = connection.execute(
            select(conversation.c.scenario_id, membership.c.id.label("membership_id"))
            .join(membership, (membership.c.site_id == conversation.c.site_id)
                  & (membership.c.app_user_id == binding.initiated_by_actor_id)
                  & membership.c.revoked_at.is_(None))
            .where(conversation.c.id == binding.conversation_id)
        ).one()
    raw_results: list[object] = []
    request_id = uuid4()
    deps = AgentDepsV1(
        actor_id=binding.initiated_by_actor_id, site_id=binding.site_id,
        membership_id=context.membership_id, request_id=request_id,
        agent_run_id=resume.agent_run_id, conversation_id=binding.conversation_id,
        scenario_id=context.scenario_id, scenario_version_id=binding.scenario_version_id,
        policy_version=POLICY_GENERATION, clock=lambda: datetime.now(timezone.utc),
        projection_reader=ShortTransactionScenarioProjectionReader(
            projection_reader, open_site_context, binding.site_id
        ), connection=None, remaining_budget=AgentBudgetV1(),
        tool_result_sink=raw_results.append,
    )
    claimed = ClaimedAgentRunV1(
        resume.agent_run_id, binding.conversation_id, context.scenario_id,
        binding.scenario_version_id, binding.site_id, binding.initiated_by_actor_id,
        context.membership_id, "", (),
    )
    try:
        granted = compose_capabilities(CapabilityGrantContextV1(
            role=PLANNER_ROLE, site_id=binding.site_id,
            feature_policy=enabled_feature_policy(settings),
            conversation_id=binding.conversation_id,
            conversation_site_id=binding.site_id,
        ))
        runtime = runtime_factory(
            settings=settings, capabilities=granted, deps=deps,
            answer_type=GroundedAnswerV1,
        )
        outcome = execute_turn(
            runtime, deps, prompt="", calculation_results=raw_results,
            history=resume.history,
            approvals=(AgentApprovalDecisionV1(tool_call_id=resume.tool_call_id, approved=True),),
        )
    except Exception as exc:  # noqa: BLE001
        outcome = failed_outcome_for_exception(exc)
    with open_site_context(binding.site_id) as connection:
        finalize_agent_run(
            conversations, proposals, connection, claimed=claimed,
            status=terminal_status(outcome), payload=activity_payload(outcome, deps),
            request_id=request_id,
        )


@router.post("", response_model=ApprovalOut, responses=_RESPONSES)
def create_approval(body: ApprovalRequestIn, idempotency_key: IdempotencyKey, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), settings: Settings = Depends(get_settings), approvals: ApprovalRepository = Depends(get_approval_repository), audit_writer: AuditWriter = Depends(get_audit_writer), conversations: ConversationRepository = Depends(get_conversation_repository), schedule_runs: ScheduleRunRepository = Depends(get_schedule_run_repository), baselines: SiteBaselineReader = Depends(get_site_baseline_reader), now: datetime = Depends(get_clock)):
    if "scheduling_baseline_enabled" not in enabled_feature_policy(settings):
        return problem_response(status=403, code="approval_not_granted", title="Approval is not available", detail="Current policy does not grant baseline approval.")
    conversation_id = schedule_runs.get_conversation_for_run(connection, run_id=body.schedule_run_id, site_id=session.site_id)
    if conversation_id is None:
        return problem_response(status=404, code="candidate_not_found", title="Candidate not found", detail="No candidate is visible in this site.")
    operation = f"request_approval:{body.schedule_run_id}"
    _, _, body_hash = contract_digest(body.model_dump(mode="json"))
    stored = schedule_runs.get_idempotent_result(connection, site_id=session.site_id, actor_id=session.app_user_id, operation=operation, idempotency_key=idempotency_key)
    if stored is not None:
        if stored.body_hash != body_hash:
            return problem_response(status=409, code="idempotency_key_conflict", title="Idempotency key conflict", detail="The idempotency key was already used with a different request body.")
        # Re-derive the presented state instead of replaying the payload frozen
        # at creation: that payload says `pending` forever, so once the window
        # passed, a replayed POST contradicted GET on the same binding.
        replayed = approvals.get(connection, approval_id=UUID(stored.response_payload["approval_id"]), site_id=session.site_id)
        if replayed is not None:
            return _out(replayed, now)
        return ApprovalOut.model_validate(stored.response_payload)
    try:
        result = request_approval(connection, command=RequestApprovalCommandV1(site_id=session.site_id, actor_id=session.app_user_id, schedule_run_id=body.schedule_run_id, expected_resource_version=body.expected_resource_version, expected_baseline_schedule_version=body.expected_baseline_schedule_version, request_effect_key=f"command:{session.app_user_id}:{operation}:{idempotency_key}", request_id=uuid4(), conversation_id=conversation_id), schedule_runs=schedule_runs, baselines=baselines, approvals=approvals, audit_writer=audit_writer, conversations=conversations, approval_expiry_seconds=settings.approval_expiry_seconds, scheduling_baseline_enabled=settings.scheduling_baseline_enabled, clock=lambda: now)
    except ApprovalRequestError as exc:
        return problem_response(status=_ERROR_STATUS.get(exc.code, 422), code=exc.code, title="Approval request could not be completed", detail="The candidate cannot be approved with the supplied binding.")
    except IntegrityError:
        # `uq_approval_request_pending_run` / `uq_approval_request_effect` lost a
        # race the read-then-write checks above cannot close. A concurrent caller
        # already created the binding, so this is a conflict, never a 500.
        return problem_response(status=409, code="approval_already_pending", title="A decision is already pending", detail="Another request already created a pending approval for this candidate.")
    output = _out(result.binding, now)
    # `_store_idempotent_result` is the name declared on `ScheduleRunRepository`
    # (ports/schedule_run.py) and used by `enqueue_compute` / `cancel_schedule_run`.
    # Underscore-from-a-router reads badly, but it is a declared port member, not
    # a reach into a private implementation detail.
    schedule_runs._store_idempotent_result(connection, site_id=session.site_id, actor_id=session.app_user_id, operation=operation, idempotency_key=idempotency_key, body_hash=body_hash, response_payload=output.model_dump(mode="json"))
    return output


@router.post("/{approval_id}/decision", response_model=ApprovalOut, responses=_DECISION_RESPONSES)
def decide_approval_route(approval_id: UUID, body: ApprovalDecisionIn, idempotency_key: IdempotencyKey, connection: Connection = Depends(get_site_context), post_commit: PostCommitActions = Depends(get_post_commit_actions), session: ResolvedSession = Depends(get_session), settings: Settings = Depends(get_settings), approvals: ApprovalRepository = Depends(get_approval_repository), audit_writer: AuditWriter = Depends(get_audit_writer), conversations: ConversationRepository = Depends(get_conversation_repository), schedule_runs: ScheduleRunRepository = Depends(get_schedule_run_repository), baselines: SiteBaselineReader = Depends(get_site_baseline_reader), baseline_writer: SiteBaselineWriter = Depends(get_site_baseline_writer), memberships: MembershipReader = Depends(get_membership_reader), runtime_factory: AgentRuntimeFactory = Depends(get_agent_runtime_factory), compose_capabilities: CapabilityComposer = Depends(get_capability_registry), projection_reader: ScenarioProjectionReader = Depends(get_projection_reader), proposals: ProposalRepository = Depends(get_proposal_repository), open_site_context: SiteContextOpener = Depends(get_site_context_opener), now: datetime = Depends(get_clock)):
    if "scheduling_baseline_enabled" not in enabled_feature_policy(settings):
        return problem_response(status=403, code="approval_not_granted", title="Approval is not available", detail="Current policy does not grant baseline approval.")
    operation = f"decide_approval:{approval_id}"
    _, _, body_hash = contract_digest(body.model_dump(mode="json"))
    stored = schedule_runs.get_idempotent_result(connection, site_id=session.site_id, actor_id=session.app_user_id, operation=operation, idempotency_key=idempotency_key)
    if stored is not None:
        if stored.body_hash != body_hash:
            return problem_response(status=409, code="idempotency_key_conflict", title="Idempotency key conflict", detail="The idempotency key was already used with a different request body.")
        problem = stored.response_payload.get("_decision_problem")
        if problem is not None:
            return problem_response(status=409, code=f"approval_{problem['outcome']}", title="Approval is no longer current", detail="Refresh or rerun before making another decision.", extra=_context(problem["expected"], problem["current"]))
        replayed = approvals.get(connection, approval_id=approval_id, site_id=session.site_id)
        if replayed is None:
            return problem_response(status=404, code="approval_not_found", title="Approval not found", detail="No approval is visible in this site.")
        if replayed.state in ("expired", "stale"):
            return problem_response(status=409, code=f"approval_{replayed.state}", title="Approval is no longer current", detail="Refresh or rerun before making another decision.")
        return _out(replayed, now)
    decision_request_id = uuid4()
    try:
        result = decide_approval(connection, command=DecideApprovalCommandV1(site_id=session.site_id, actor_id=session.app_user_id, approval_id=approval_id, decision=body.decision, expected_resource_version=body.expected_resource_version, request_id=decision_request_id), approvals=approvals, schedule_runs=schedule_runs, baselines=baselines, baseline_writer=baseline_writer, memberships=memberships, audit_writer=audit_writer, conversations=conversations, scheduling_baseline_enabled=settings.scheduling_baseline_enabled, clock=lambda: now)
    except DecideApprovalError as exc:
        if isinstance(exc, (PostWriteApprovalNotPendingError, BaselineConcurrentlyMovedError)):
            raise
        if exc.code in {"approval_not_pending", "stale_resource_version"}:
            denied = approvals.get(connection, approval_id=approval_id, site_id=session.site_id)
            if denied is not None:
                audit_writer.append(connection, AuditEnvelopeV1(
                    audit_id=uuid4(), attempt_id=uuid4(), request_id=decision_request_id,
                    site_id=session.site_id, initiated_by_actor_id=denied.initiated_by_actor_id,
                    decided_by_actor_id=session.app_user_id, conversation_id=denied.conversation_id,
                    agent_run_id=denied.agent_run_id, approval_id=denied.approval_id,
                    schedule_run_id=denied.schedule_run_id, action=denied.action,
                    outcome="approval_denied", success=False,
                    effect_key=denied.request_effect_key,
                    before_version=denied.baseline_schedule_version, after_version=None,
                    safe_summary=denied.consequence_summary,
                    parameter_hash=denied.parameter_hash,
                    consequence_hash=denied.consequence_hash,
                    policy_version=denied.policy_version, app_version="0.1.0",
                    worker_facts=WorkerFactsV1(), evidence_refs=(), occurred_at=now,
                ))
        return problem_response(status=_ERROR_STATUS.get(exc.code, 422), code=exc.code, title="Approval decision could not be completed", detail=_DECISION_DETAIL.get(exc.code, _DECISION_DETAIL_FALLBACK), extra=_context(exc.expected, exc.current))
    output = _out(result.binding, now)
    if result.outcome in ("expired", "stale"):
        # Returning (not raising) commits the terminal TX3 bundle.
        payload = output.model_dump(mode="json")
        payload["_decision_problem"] = {"outcome": result.outcome, "expected": result.expected, "current": result.current}
        schedule_runs._store_idempotent_result(connection, site_id=session.site_id, actor_id=session.app_user_id, operation=operation, idempotency_key=idempotency_key, body_hash=body_hash, response_payload=payload)
        return problem_response(status=409, code=f"approval_{result.outcome}", title="Approval is no longer current", detail="Refresh or rerun before making another decision.", extra=_context(result.expected, result.current))
    schedule_runs._store_idempotent_result(connection, site_id=session.site_id, actor_id=session.app_user_id, operation=operation, idempotency_key=idempotency_key, body_hash=body_hash, response_payload=output.model_dump(mode="json"))
    if result.resume is not None:
        post_commit.add(lambda: _drive_resumed_turn(
            resume=result.resume, binding=result.binding, settings=settings,
            runtime_factory=runtime_factory, compose_capabilities=compose_capabilities,
            projection_reader=projection_reader, conversations=conversations,
            proposals=proposals, open_site_context=open_site_context,
        ))
    return output


@router.get("/{approval_id}", response_model=ApprovalOut, responses=_RESPONSES)
def get_approval(approval_id: UUID, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), approvals: ApprovalRepository = Depends(get_approval_repository), now: datetime = Depends(get_clock)):
    binding = approvals.get(connection, approval_id=approval_id, site_id=session.site_id)
    if binding is None:
        return problem_response(status=404, code="approval_not_found", title="Approval not found", detail="No approval is visible in this site.")
    return _out(binding, now)


@router.get("", response_model=ApprovalListOut, responses=_RESPONSES)
def list_approvals(schedule_run_id: UUID = Query(), connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), approvals: ApprovalRepository = Depends(get_approval_repository), now: datetime = Depends(get_clock)):
    return ApprovalListOut(items=[_out(item, now) for item in approvals.list_for_schedule_run(connection, schedule_run_id=schedule_run_id, site_id=session.site_id)])
