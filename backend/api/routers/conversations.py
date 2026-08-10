"""Durable conversation commands and bounded timeline reads."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import Connection

from api.deps import get_conversation_repository, get_session, get_site_context
from api.schemas import (
    AcceptedTurnOut,
    ActivityItemOut,
    ConversationCreateIn,
    ConversationListOut,
    ConversationOut,
    MessageCreateIn,
    ProblemDetailsV1,
    TimelineOut,
)
from application.contracts.persisted_event import PersistedEventV1
from application.ports.conversation import ConversationRepository, ConversationV1
from application.ports.session import ResolvedSession
from application.use_cases.accept_turn import accept_turn

router = APIRouter(prefix="/conversations", tags=["conversations"])
_PROBLEM_RESPONSES = {401: {"model": ProblemDetailsV1}, 403: {"model": ProblemDetailsV1}, 404: {"model": ProblemDetailsV1}, 422: {"model": ProblemDetailsV1}}


def _conversation(value: ConversationV1) -> ConversationOut:
    return ConversationOut(id=value.id, scenario_id=value.scenario_id, scenario_version_id=value.scenario_version_id, resource_version=value.resource_version)


def _activity(event: PersistedEventV1) -> ActivityItemOut:
    """Project one persisted envelope into its planner-visible activity item.

    `sequence` is carried down from the envelope and rendered as a string; see
    ActivityItemOut.
    """
    return ActivityItemOut(**event.payload.__dict__, sequence=str(event.sequence))


@router.post("", status_code=status.HTTP_201_CREATED, response_model=ConversationOut, responses=_PROBLEM_RESPONSES)
def create_conversation(body: ConversationCreateIn, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), repository: ConversationRepository = Depends(get_conversation_repository)) -> ConversationOut:
    value = repository.create(connection, scenario_id=body.scenario_id, scenario_version_id=body.scenario_version_id, site_id=session.site_id, actor_id=session.app_user_id)
    # An unknown scenario, an unknown version, a version belonging to another
    # scenario, and anything owned by another site all land here with one
    # indistinguishable shape (AD-3 non-disclosure).
    if value is None:
        raise HTTPException(status_code=404)
    return _conversation(value)


@router.get("", response_model=ConversationListOut, responses=_PROBLEM_RESPONSES)
def list_conversations(scenario_id: UUID, limit: int = Query(100, ge=1, le=100), connection: Connection = Depends(get_site_context), repository: ConversationRepository = Depends(get_conversation_repository)) -> ConversationListOut:
    page = repository.list_for_scenario(connection, scenario_id=scenario_id, limit=limit)
    return ConversationListOut(items=[_conversation(v) for v in page.items], limit=page.limit, has_more=page.has_more)


@router.post("/{conversation_id}/messages", status_code=status.HTTP_201_CREATED, response_model=AcceptedTurnOut, responses=_PROBLEM_RESPONSES)
def send_message(conversation_id: UUID, body: MessageCreateIn, connection: Connection = Depends(get_site_context), session: ResolvedSession = Depends(get_session), repository: ConversationRepository = Depends(get_conversation_repository)) -> AcceptedTurnOut:
    value = accept_turn(repository, connection, conversation_id=conversation_id, site_id=session.site_id, actor_id=session.app_user_id, text=body.text)
    if value is None:
        raise HTTPException(status_code=404)
    return AcceptedTurnOut(activity=_activity(value.event), resource_version=value.resource_version, agent_run_status=value.agent_run_status, sequence=str(value.event.sequence))


@router.get("/{conversation_id}/timeline", response_model=TimelineOut, responses=_PROBLEM_RESPONSES)
def timeline(conversation_id: UUID, limit: int = Query(200, ge=1, le=200), connection: Connection = Depends(get_site_context), repository: ConversationRepository = Depends(get_conversation_repository)) -> TimelineOut:
    value = repository.timeline(connection, conversation_id=conversation_id, limit=limit)
    if value is None:
        raise HTTPException(status_code=404)
    return TimelineOut(conversation_id=value.conversation_id, resource_version=value.resource_version, latest_agent_run_status=value.latest_agent_run_status, items=[_activity(e) for e in value.events], limit=value.limit, has_more=value.has_more)
