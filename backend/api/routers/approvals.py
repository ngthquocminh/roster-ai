"""Request, inspect, and decide exact baseline-approval bindings."""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import Connection, select
from sqlalchemy.exc import IntegrityError
from pydantic import ValidationError

from api.deps import AgentRuntimeFactory, CapabilityComposer, PostCommitActions, SiteContextOpener, get_agent_runtime_factory, get_approval_repository, get_audit_reader, get_audit_writer, get_capability_registry, get_clock, get_conversation_repository, get_membership_reader, get_post_commit_actions, get_projection_reader, get_proposal_repository, get_schedule_run_repository, get_session, get_settings, get_site_baseline_reader, get_site_baseline_writer, get_site_context, get_site_context_opener
from api.problems import problem_response
from api.schemas import (
    ApprovalDecisionIn, ApprovalListOut, ApprovalOut, ApprovalRequestIn,
    ApprovalDecisionProvenanceOut, ApprovalRequestProvenanceOut,
    AuditRecordProvenanceOut, BaselinePromotionProvenanceOut,
    DecisionProvenanceOut, DraftProvenanceOut, EvidenceClaimProvenanceOut,
    ProblemDetailsV1, RunProgressProvenanceOut, SolverRunProvenanceOut,
    ToolProposalProvenanceOut,
)
from application.capabilities.installed import enabled_feature_policy
from application.ports.approval import ApprovalRepository, AuditReader, AuditWriter
from application.ports.conversation import ConversationRepository
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
from application.contracts.approval_binding import presented_approval_state
from application.contracts.decision_provenance import (
    ApprovalDecisionProvenanceV1, ApprovalRequestProvenanceV1,
    AuditRecordProvenanceV1, BaselinePromotionProvenanceV1,
    DraftProvenanceV1, EvidenceClaimProvenanceV1, RunProgressProvenanceV1,
    SolverRunProvenanceV1, ToolProposalProvenanceV1,
)
from application.queries.decision_provenance import query_decision_provenance
from application.contracts.grounding import GroundedAnswerV1
from application.capabilities.deps import AgentDepsV1
from application.capabilities.registry import CapabilityGrantContextV1, PLANNER_ROLE, POLICY_GENERATION
from application.use_cases.execute_turn import activity_payload, execute_turn, failed_outcome_for_exception, terminal_status
from application.use_cases.finalize_agent_run import finalize_agent_run
from adapters.postgres.short_transaction_projection import ShortTransactionScenarioProjectionReader
from adapters.postgres.schema import conversation, membership
from settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


class ResumedTurnSuspendedError(RuntimeError):
    """A resumed turn deferred a second approval; Decision 8 covers only one.

    `terminal_status` maps a suspended outcome to `approval_required` -- a status
    whose entire meaning is "a binding is pending on this run". The resume path
    creates no binding, so finalising a second suspension that way parks the run
    in a state `get_pending_for_agent_run` reports as empty and `claim_queued_run`
    never reclaims: stranded permanently, silently. Refusing the chain keeps the
    run terminal and honest. If a later story needs chained approvals, the
    binding-creating branch in `conversations.py` becomes a shared helper -- it is
    not copied here (EAD-5: no second resume mechanism).
    """
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=40)]
_RESPONSES = {403: {"model": ProblemDetailsV1}, 404: {"model": ProblemDetailsV1}, 409: {"model": ProblemDetailsV1}, 422: {"model": ProblemDetailsV1}}
#: The decision route additionally publishes 500: `approval_payload_unreadable`
#: is a stable, documented code (an agent-backed binding whose stored payload
#: cannot drive the resumed turn), not the generic unhandled-error shape, so it
#: belongs in the contract rather than surfacing as an undeclared status.
_DECISION_RESPONSES = {**_RESPONSES, 500: {"model": ProblemDetailsV1}}
_PROVENANCE_RESPONSES = {404: {"model": ProblemDetailsV1}}

#: Status per stable problem code (AD-13). `approval_not_granted` is 403 at BOTH
#: sites -- the router's feature-policy pre-check and the use case's own
#: `ApprovalNotGrantedError` describe the identical condition, and Task 8 fixes
#: it at 403, so mapping the second one to 422 published two statuses for one
#: state.
#: NOTE: `agent_run_not_cancellable` is deliberately ABSENT. It is never rendered
#: by this module -- `AgentRunNotQueuedError` must ESCAPE the endpoint so the
#: request dependency rolls TX2 back, and `api/main.py`'s
#: `rollback_required_decision_problem` is its single source of status and copy.
#: The same applies to the post-write `approval_not_pending`
#: (`PostWriteApprovalNotPendingError`) and to `approval_payload_unreadable`.
#:
#: `stale_baseline_version` DOES belong here, but for the OTHER route: the CREATE
#: path raises `StaleBaselineVersionError` as an ordinary pre-write refusal it
#: catches and returns. The decision path's same-named code comes from
#: `BaselineConcurrentlyMovedError`, which escapes and is rendered in `main.py`.
#: One wire code, two routes, two mechanisms -- deleting this entry silently
#: demoted the create route's refusal to a 422.
_ERROR_STATUS = {
    "candidate_not_found": 404,
    "approval_not_granted": 403,
    "approval_already_pending": 409,
    "candidate_not_promotable": 409,
    "stale_resource_version": 409,
    "stale_baseline_version": 409,
    "approval_not_found": 404,
    "approval_not_pending": 409,
}

#: Detail per decision-route problem code. `approval_not_granted` is a policy
#: refusal, not a stale binding.
_DECISION_DETAIL = {
    "approval_not_granted": "Current policy does not grant baseline approval.",
    "approval_not_found": "No approval is visible in this site.",
    "approval_not_pending": "The approval already reached a terminal state.",
    "stale_resource_version": "The approval changed since the version you pinned.",
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
    state = presented_approval_state(binding, now)
    return ApprovalOut(approval_id=binding.approval_id, state=state, schedule_run_id=binding.schedule_run_id, candidate_schedule_version_id=binding.candidate_schedule_version_id, baseline_schedule_version=binding.baseline_schedule_version, scenario_version_id=binding.scenario_version_id, consequence_summary=binding.consequence_summary, policy_version=binding.policy_version, agent_run_id=binding.agent_run_id, created_at=binding.created_at, expires_at=binding.expires_at, resource_version=binding.resource_version)


def _provenance_item_out(item):
    common = dict(
        occurred_at=item.occurred_at, item_type=item.item_type, site_id=item.site_id,
        actor_id=item.actor_id, initiated_by_actor_id=item.initiated_by_actor_id,
        decided_by_actor_id=item.decided_by_actor_id, request_id=item.request_id,
        attempt_id=item.attempt_id, conversation_id=item.conversation_id,
        agent_run_id=item.agent_run_id, tool_call_id=item.tool_call_id,
        approval_id=item.approval_id, job_attempt_id=item.job_attempt_id,
        schedule_run_id=item.schedule_run_id, audit_id=item.audit_id,
        schedule_version_id=item.schedule_version_id,
        scenario_version_id=item.scenario_version_id,
        evidence_refs=item.evidence_refs, schema_version=item.schema_version,
    )
    if isinstance(item, SolverRunProvenanceV1):
        return SolverRunProvenanceOut(**common, status=item.status, reason=item.reason,
            baseline_schedule_version=item.baseline_schedule_version,
            candidate_schedule_version_id=item.candidate_schedule_version_id,
            comparison_status=item.comparison_status, comparison_reason=item.comparison_reason,
            metrics=item.metrics)
    if isinstance(item, RunProgressProvenanceV1):
        return RunProgressProvenanceOut(**common, status=item.status, reason=item.reason,
                                        resource_version=item.resource_version)
    if isinstance(item, DraftProvenanceV1):
        return DraftProvenanceOut(**common, proposal_id=item.proposal_id,
                                  proposal_version_id=item.proposal_version_id,
                                  consequence_summary=item.consequence_summary)
    if isinstance(item, EvidenceClaimProvenanceV1):
        return EvidenceClaimProvenanceOut(**common, claim=item.claim, value=item.value,
                                          unit=item.unit)
    if isinstance(item, ToolProposalProvenanceV1):
        return ToolProposalProvenanceOut(**common, tool_name=item.tool_name)
    if isinstance(item, ApprovalRequestProvenanceV1):
        return ApprovalRequestProvenanceOut(**common, state=item.state,
            consequence_summary=item.consequence_summary, parameter_hash=item.parameter_hash,
            consequence_hash=item.consequence_hash, policy_version=item.policy_version,
            expires_at=item.expires_at)
    if isinstance(item, ApprovalDecisionProvenanceV1):
        return ApprovalDecisionProvenanceOut(**common, outcome=item.outcome, state=item.state)
    if isinstance(item, AuditRecordProvenanceV1):
        return AuditRecordProvenanceOut(**common, action=item.action, outcome=item.outcome,
            success=item.success, safe_summary=item.safe_summary,
            parameter_hash=item.parameter_hash, consequence_hash=item.consequence_hash,
            policy_version=item.policy_version, app_version=item.app_version,
            worker_facts=item.worker_facts)
    if isinstance(item, BaselinePromotionProvenanceV1):
        return BaselinePromotionProvenanceOut(**common, before_version=item.before_version,
                                              after_version=item.after_version)
    raise TypeError(f"unsupported provenance item: {type(item).__name__}")


def _drive_resumed_turn(*, resume, binding, settings, runtime_factory, compose_capabilities,
                        projection_reader, conversations, proposals, open_site_context) -> None:
    """Drive one already-resumed run after TX2 has committed.

    NOTHING HERE MAY RAISE. This runs in the request's post-commit stage, which
    FastAPI executes after the response has already been sent; an exception at
    this point cannot become a response (Starlette raises "Caught handled
    exception, but response already started") and would tear the connection down
    mid-body while abandoning the run in `agent_running`. The promotion itself is
    already durable by then -- consumed binding, moved pointer, audit row -- so a
    failure here must degrade the TURN, never the transaction that preceded it.

    Setup failure is the one case that cannot be finalised: `deps` and the claim
    are built from the query below, so without it there is nothing to finalise
    through. That leaves the run `agent_running` for Epic 3's recovery sweep --
    the same documented outcome as the initial-turn route (`conversations.py`).
    """
    try:
        with open_site_context(binding.site_id) as connection:
            context = connection.execute(
                select(conversation.c.scenario_id, membership.c.id.label("membership_id"))
                .join(membership, (membership.c.site_id == conversation.c.site_id)
                      & (membership.c.app_user_id == binding.initiated_by_actor_id)
                      & membership.c.revoked_at.is_(None))
                .where(conversation.c.id == binding.conversation_id)
            ).one()
    except Exception:  # noqa: BLE001
        # `.one()` raises `NoResultFound` if the initiating actor's membership was
        # revoked between TX2's commit and this read -- revalidation proved it
        # active inside the transaction, so this is a genuine race, not a guard.
        logger.exception(
            "resumed turn setup failed for agent run %s; run left non-terminal for recovery",
            resume.agent_run_id,
        )
        return
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
        if outcome.status == "suspended":
            raise ResumedTurnSuspendedError(
                "a resumed turn requested a second approval; chaining is not supported"
            )
    except Exception as exc:  # noqa: BLE001
        logger.exception("resumed turn failed for agent run %s; finalizing as terminal",
                         resume.agent_run_id)
        outcome = failed_outcome_for_exception(exc)
    try:
        with open_site_context(binding.site_id) as connection:
            finalize_agent_run(
                conversations, proposals, connection, claimed=claimed,
                status=terminal_status(outcome), payload=activity_payload(outcome, deps),
                request_id=request_id,
            )
    except Exception:  # noqa: BLE001
        # `finish_agent_run` raises if the run left `agent_running` under us, and
        # `activity_payload` is evaluated here too. Either way the promotion has
        # committed and the response is sent; the only correct action left is to
        # record it loudly rather than crash a response already on the wire.
        logger.exception(
            "resumed turn for agent run %s could not be finalized; run left non-terminal",
            resume.agent_run_id,
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
        # Decision 7 enumerates the denial-audit refusals by CODE, but the code is
        # not unique to a raise site: `approval_not_pending` is raised from THREE
        # places, not the two the story states -- the admission check, TX2's
        # consume-CAS closer (`PostWriteApprovalNotPendingError`, re-raised above),
        # and TX3's terminalize-CAS closer (`ConcurrentDecisionError`). Matching on
        # the code alone audited the third by accident. Discriminate by TYPE so
        # each site's participation is a decision rather than a coincidence.
        #
        # `ConcurrentDecisionError` IS audited, deliberately: it is a denied
        # consequential attempt against a binding resolved in this site, and
        # `terminalize` returning `None` means nothing was written, so the
        # transaction is healthy and the row commits. That satisfies FR21 on the
        # same terms as the admission-check denial; it extends Decision 7's
        # enumeration by one site rather than contradicting its rule.
        if exc.code in {"approval_not_pending", "stale_resource_version"} and not isinstance(
            exc, PostWriteApprovalNotPendingError
        ):
            denied = approvals.get(connection, approval_id=approval_id, site_id=session.site_id)
            if denied is not None:
                try:
                    candidate = schedule_runs.get_candidate(
                        connection, schedule_run_id=denied.schedule_run_id, site_id=session.site_id
                    )
                except ValidationError:
                    # A stored `schedule_version.payload` that no longer validates is a
                    # PERMANENT condition: a retry cannot heal it, and letting it escape
                    # this handler would roll back and lose the FR21 denial row for good.
                    # Record honest absence so the row and its 409 both still commit.
                    # A transactional fault is deliberately NOT caught -- it is transient,
                    # and this arm stores no idempotent result, so the client's retry
                    # re-enters here and writes a row carrying the real references.
                    candidate = None
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
                    worker_facts=WorkerFactsV1(),
                    # These references identify the candidate the refused attempt
                    # targeted; the admission check consulted no candidate evidence.
                    evidence_refs=candidate.evidence_refs if candidate is not None else (),
                    occurred_at=now,
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


@router.get("/provenance", response_model=DecisionProvenanceOut, responses=_PROVENANCE_RESPONSES)
def get_provenance(
    schedule_run_id: UUID = Query(),
    connection: Connection = Depends(get_site_context),
    session: ResolvedSession = Depends(get_session),
    schedule_runs: ScheduleRunRepository = Depends(get_schedule_run_repository),
    approvals: ApprovalRepository = Depends(get_approval_repository),
    audit_reader: AuditReader = Depends(get_audit_reader),
    conversations: ConversationRepository = Depends(get_conversation_repository),
    now: datetime = Depends(get_clock),
):
    result = query_decision_provenance(
        connection, schedule_run_id=schedule_run_id, site_id=session.site_id,
        schedule_runs=schedule_runs, approvals=approvals, audit_reader=audit_reader,
        conversations=conversations, clock=lambda: now,
    )
    if result is None:
        return problem_response(
            status=404, code="schedule_run_not_found", title="Schedule run not found",
            detail="No schedule run with that identifier is visible in this site.",
        )
    return DecisionProvenanceOut(
        schedule_run_id=result.schedule_run_id, site_id=result.site_id,
        items=[_provenance_item_out(item) for item in result.items],
        schema_version=result.schema_version,
    )


@router.get("/{approval_id}", response_model=ApprovalOut, responses=_RESPONSES)
def get_approval(approval_id: UUID, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), approvals: ApprovalRepository = Depends(get_approval_repository), now: datetime = Depends(get_clock)):
    binding = approvals.get(connection, approval_id=approval_id, site_id=session.site_id)
    if binding is None:
        return problem_response(status=404, code="approval_not_found", title="Approval not found", detail="No approval is visible in this site.")
    return _out(binding, now)


@router.get("", response_model=ApprovalListOut, responses=_RESPONSES)
def list_approvals(schedule_run_id: UUID = Query(), connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), approvals: ApprovalRepository = Depends(get_approval_repository), now: datetime = Depends(get_clock)):
    return ApprovalListOut(items=[_out(item, now) for item in approvals.list_for_schedule_run(connection, schedule_run_id=schedule_run_id, site_id=session.site_id)])
