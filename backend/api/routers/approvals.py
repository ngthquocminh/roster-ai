"""Request and inspect exact baseline-approval bindings (TX1 only)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy import Connection

from api.deps import get_approval_repository, get_audit_writer, get_conversation_repository, get_schedule_run_repository, get_session, get_settings, get_site_baseline_reader, get_site_context
from api.problems import problem_response
from api.schemas import ApprovalListOut, ApprovalOut, ApprovalRequestIn, ProblemDetailsV1
from application.capabilities.installed import enabled_feature_policy
from application.ports.approval import ApprovalRepository, AuditWriter
from application.ports.conversation import ConversationRepository
from application.ports.schedule_run import ScheduleRunRepository
from application.ports.session import ResolvedSession
from application.ports.site_baseline import SiteBaselineReader
from application.use_cases.request_approval import ApprovalRequestError, RequestApprovalCommandV1, request_approval
from settings import Settings

router = APIRouter(prefix="/approvals", tags=["approvals"])
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=40)]
_RESPONSES = {403: {"model": ProblemDetailsV1}, 404: {"model": ProblemDetailsV1}, 409: {"model": ProblemDetailsV1}, 422: {"model": ProblemDetailsV1}}


def _out(binding) -> ApprovalOut:
    state = "expired" if binding.state == "pending" and binding.expires_at <= datetime.now(timezone.utc) else binding.state
    return ApprovalOut(approval_id=binding.approval_id, state=state, schedule_run_id=binding.schedule_run_id, candidate_schedule_version_id=binding.candidate_schedule_version_id, baseline_schedule_version=binding.baseline_schedule_version, consequence_summary=binding.consequence_summary, policy_version=binding.policy_version, expires_at=binding.expires_at, resource_version=binding.resource_version)


@router.post("", response_model=ApprovalOut, responses=_RESPONSES)
def create_approval(body: ApprovalRequestIn, idempotency_key: IdempotencyKey, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), settings: Settings = Depends(get_settings), approvals: ApprovalRepository = Depends(get_approval_repository), audit_writer: AuditWriter = Depends(get_audit_writer), conversations: ConversationRepository = Depends(get_conversation_repository), schedule_runs: ScheduleRunRepository = Depends(get_schedule_run_repository), baselines: SiteBaselineReader = Depends(get_site_baseline_reader)):
    if "scheduling_baseline_enabled" not in enabled_feature_policy(settings):
        return problem_response(status=403, code="approval_not_granted", title="Approval is not available", detail="Current policy does not grant baseline approval.")
    conversation_id = schedule_runs.get_conversation_for_run(connection, run_id=body.schedule_run_id, site_id=session.site_id)
    if conversation_id is None:
        return problem_response(status=404, code="candidate_not_found", title="Candidate not found", detail="No candidate is visible in this site.")
    try:
        binding = request_approval(connection, command=RequestApprovalCommandV1(site_id=session.site_id, actor_id=session.app_user_id, schedule_run_id=body.schedule_run_id, expected_resource_version=body.expected_resource_version, expected_baseline_schedule_version=body.expected_baseline_schedule_version, request_effect_key=f"command:{session.app_user_id}:request_approval:{idempotency_key}", request_id=uuid4(), conversation_id=conversation_id), schedule_runs=schedule_runs, baselines=baselines, approvals=approvals, audit_writer=audit_writer, conversations=conversations, approval_expiry_seconds=settings.approval_expiry_seconds, scheduling_baseline_enabled=settings.scheduling_baseline_enabled, clock=lambda: datetime.now(timezone.utc))
    except ApprovalRequestError as exc:
        status = 404 if exc.code == "candidate_not_found" else 409 if exc.code.startswith("stale_") or exc.code == "candidate_not_promotable" else 422
        return problem_response(status=status, code=exc.code, title="Approval request could not be completed", detail="The candidate cannot be approved with the supplied binding.")
    return _out(binding)


@router.get("/{approval_id}", response_model=ApprovalOut, responses=_RESPONSES)
def get_approval(approval_id: UUID, connection: Connection = Depends(get_site_context), approvals: ApprovalRepository = Depends(get_approval_repository)):
    binding = approvals.get(connection, approval_id=approval_id)
    if binding is None:
        return problem_response(status=404, code="approval_not_found", title="Approval not found", detail="No approval is visible in this site.")
    return _out(binding)


@router.get("", response_model=ApprovalListOut, responses=_RESPONSES)
def list_approvals(schedule_run_id: UUID = Query(), connection: Connection = Depends(get_site_context), approvals: ApprovalRepository = Depends(get_approval_repository)):
    return ApprovalListOut(items=[_out(item) for item in approvals.list_for_schedule_run(connection, schedule_run_id=schedule_run_id)])
