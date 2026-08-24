"""Site-scoped, network-free AgentRuntime availability read."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import Connection

from api.deps import (
    AgentRuntimeFactory,
    get_agent_runtime_factory,
    get_conversation_repository,
    get_session,
    get_settings,
    get_site_context,
)
from api.schemas import ProblemDetailsV1
from application.ports.conversation import ConversationRepository
from application.ports.session import ResolvedSession
from application.use_cases.agent_availability import (
    AgentAvailabilityV1,
    get_agent_availability,
)
from settings import Settings

router = APIRouter(tags=["agent availability"])
_PROBLEM_RESPONSES = {
    401: {"model": ProblemDetailsV1},
    403: {"model": ProblemDetailsV1},
    404: {"model": ProblemDetailsV1},
    422: {"model": ProblemDetailsV1},
}


@router.get(
    "/agent-availability",
    response_model=AgentAvailabilityV1,
    responses=_PROBLEM_RESPONSES,
)
def agent_availability(
    scenario_id: UUID,
    connection: Connection = Depends(get_site_context),
    session: ResolvedSession = Depends(get_session),
    repository: ConversationRepository = Depends(get_conversation_repository),
    runtime_factory: AgentRuntimeFactory = Depends(get_agent_runtime_factory),
    settings: Settings = Depends(get_settings),
) -> AgentAvailabilityV1:
    # Required to place the read in the selected scenario's authenticated UI
    # context. Availability itself is intentionally site-wide, not scoped to a
    # conversation or scenario, so a new conversation can observe an outage.
    _ = scenario_id
    return get_agent_availability(
        lambda: runtime_factory(settings=settings),
        repository,
        connection,
        site_id=session.site_id,
        recency_seconds=settings.agent_availability_recency_seconds,
    )
