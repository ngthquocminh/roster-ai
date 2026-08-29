"""Request and inspect exact baseline-approval bindings (TX1 only)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import Connection
from sqlalchemy.exc import IntegrityError

from api.deps import get_approval_repository, get_audit_writer, get_clock, get_conversation_repository, get_schedule_run_repository, get_session, get_settings, get_site_baseline_reader, get_site_context
from api.problems import problem_response
from api.schemas import ApprovalListOut, ApprovalOut, ApprovalRequestIn, ProblemDetailsV1
from application.capabilities.installed import enabled_feature_policy
from application.ports.approval import ApprovalRepository, AuditWriter
from application.ports.conversation import ConversationRepository
from application.ports.schedule_run import ScheduleRunRepository
from application.ports.session import ResolvedSession
from application.ports.site_baseline import SiteBaselineReader
from application.use_cases.request_approval import ApprovalRequestError, RequestApprovalCommandV1, request_approval
from application.contracts.canonical import contract_digest
from settings import Settings

router = APIRouter(prefix="/approvals", tags=["approvals"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=40)]
_RESPONSES = {403: {"model": ProblemDetailsV1}, 404: {"model": ProblemDetailsV1}, 409: {"model": ProblemDetailsV1}, 422: {"model": ProblemDetailsV1}}

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
}


def _out(binding, now: datetime) -> ApprovalOut:
    # EAD-7: a read that observes `now() >= expires_at` PRESENTS the binding as
    # expired and writes nothing. The terminal `expired` state materialises only
    # inside a decision-attempt transaction, which Story 4.2 owns.
    state = "expired" if binding.state == "pending" and binding.expires_at <= now else binding.state
    return ApprovalOut(approval_id=binding.approval_id, state=state, schedule_run_id=binding.schedule_run_id, candidate_schedule_version_id=binding.candidate_schedule_version_id, baseline_schedule_version=binding.baseline_schedule_version, scenario_version_id=binding.scenario_version_id, consequence_summary=binding.consequence_summary, policy_version=binding.policy_version, expires_at=binding.expires_at, resource_version=binding.resource_version)


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


@router.get("/{approval_id}", response_model=ApprovalOut, responses=_RESPONSES)
def get_approval(approval_id: UUID, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), approvals: ApprovalRepository = Depends(get_approval_repository), now: datetime = Depends(get_clock)):
    binding = approvals.get(connection, approval_id=approval_id, site_id=session.site_id)
    if binding is None:
        return problem_response(status=404, code="approval_not_found", title="Approval not found", detail="No approval is visible in this site.")
    return _out(binding, now)


@router.get("", response_model=ApprovalListOut, responses=_RESPONSES)
def list_approvals(schedule_run_id: UUID = Query(), connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), approvals: ApprovalRepository = Depends(get_approval_repository), now: datetime = Depends(get_clock)):
    return ApprovalListOut(items=[_out(item, now) for item in approvals.list_for_schedule_run(connection, schedule_run_id=schedule_run_id, site_id=session.site_id)])
