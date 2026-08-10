"""Durable conversation commands and bounded timeline reads."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Connection

from api.deps import get_conversation_repository, get_session, get_site_context
from api.schemas import AcceptedTurnOut, ActivityItemOut, ConversationCreateIn, ConversationOut, MessageCreateIn, ProblemDetailsV1, TimelineOut
from application.contracts.activity import ActivityItemV1
from application.ports.conversation import ConversationRepository, ConversationV1
from application.ports.session import ResolvedSession
from application.use_cases.accept_turn import accept_turn

router = APIRouter(prefix="/conversations", tags=["conversations"])
_PROBLEM_RESPONSES = {401: {"model": ProblemDetailsV1}, 403: {"model": ProblemDetailsV1}, 404: {"model": ProblemDetailsV1}, 422: {"model": ProblemDetailsV1}}


def _conversation(value: ConversationV1) -> ConversationOut:
    return ConversationOut(id=value.id, scenario_id=value.scenario_id, scenario_version_id=value.scenario_version_id, resource_version=value.resource_version)


def _activity(value: ActivityItemV1) -> ActivityItemOut:
    return ActivityItemOut(**value.__dict__)


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationOut, responses=_PROBLEM_RESPONSES)
def create_conversation(body: ConversationCreateIn, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), repository: ConversationRepository = Depends(get_conversation_repository)) -> ConversationOut:
    value = repository.create(connection, scenario_id=body.scenario_id, site_id=session.site_id, actor_id=session.app_user_id)
    if value is None:
        raise HTTPException(status_code=404)
    return _conversation(value)


@router.get("", response_model=list[ConversationOut], responses=_PROBLEM_RESPONSES)
def list_conversations(scenario_id: UUID, limit: int = Query(100, ge=1, le=100), connection: Connection = Depends(get_site_context), repository: ConversationRepository = Depends(get_conversation_repository)) -> list[ConversationOut]:
    return [_conversation(v) for v in repository.list_for_scenario(connection, scenario_id=scenario_id, limit=limit)]


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED, response_model=AcceptedTurnOut, responses=_PROBLEM_RESPONSES)
def send_message(conversation_id: UUID, body: MessageCreateIn, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), repository: ConversationRepository = Depends(get_conversation_repository)) -> AcceptedTurnOut:
    value = accept_turn(repository, connection, conversation_id=conversation_id, site_id=session.site_id, actor_id=session.app_user_id, text=body.text)
    if value is None:
        raise HTTPException(status_code=404)
    return AcceptedTurnOut(activity=_activity(value.activity), resource_version=value.resource_version, agent_run_status=value.agent_run_status, sequence=value.sequence)


@router.get("/{conversation_id}/timeline", response_model=TimelineOut, responses=_PROBLEM_RESPONSES)
def timeline(conversation_id: UUID, limit: int = Query(200, ge=1, le=200), connection: Connection = Depends(get_site_context), repository: ConversationRepository = Depends(get_conversation_repository)) -> TimelineOut:
    value = repository.timeline(connection, conversation_id=conversation_id, limit=limit)
    if value is None:
        raise HTTPException(status_code=404)
    return TimelineOut(conversation_id=value.conversation_id, resource_version=value.resource_version, latest_agent_run_status=value.latest_agent_run_status, items=[_activity(v) for v in value.items], limit=value.limit)
