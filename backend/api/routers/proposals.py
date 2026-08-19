"""Planner reads and idempotent commands for reversible proposals."""
from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import Connection

from api.deps import get_projection_reader, get_proposal_repository, get_session, get_site_context
from api.problems import problem_response
from api.schemas import ProblemDetailsV1, ProposalOut, ProposalRejectionIn, ProposalRevisionIn
from application.contracts.proposal import ProposalViewV1
from application.ports.proposal import ProposalRepository
from application.ports.scenario_projection import ScenarioProjectionReader
from application.ports.session import ResolvedSession
from application.use_cases.manage_proposal import (
    IdempotencyKeyConflictError,
    ProjectionUnavailableError,
    ProposalCommandError,
    RejectedProposalError,
    StaleProposalError,
    StaleResourceVersionError,
    get_proposal,
    reject_proposal,
    revise_proposal,
)

router = APIRouter(prefix="/proposals", tags=["proposals"])
_PROBLEMS = {
    401: {"model": ProblemDetailsV1}, 403: {"model": ProblemDetailsV1},
    404: {"model": ProblemDetailsV1}, 409: {"model": ProblemDetailsV1},
    422: {"model": ProblemDetailsV1}, 503: {"model": ProblemDetailsV1},
}
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=40)]

# `response_model=ProposalOut` describes the 200 body; `responses=_PROBLEMS`
# describes every error body. The return annotations are omitted deliberately:
# these handlers return either a ProposalOut or a JSONResponse problem, and
# annotating them `-> ProposalOut` while returning a JSONResponse was a lie the
# type checker could not see and the generated client inherited.
def _out(value: ProposalViewV1) -> ProposalOut:
    proposal = value.proposal
    if (
        proposal.proposal_id is None
        or proposal.proposal_version_id is None
        or proposal.scenario_id is None
        or proposal.scenario_version_id is None
    ):
        raise RuntimeError("persisted proposal is missing governed identifiers")
    return ProposalOut(
        **proposal.__dict__,
        current_scenario_version_id=value.current_scenario_version_id,
        stale=value.stale,
    )


def _not_found() -> JSONResponse:
    return problem_response(
        status=404, code="proposal_not_found", title="Proposal not found",
        detail="No proposal with that identifier is visible in this site.",
    )


def _command_problem(exc: ProposalCommandError) -> JSONResponse:
    if isinstance(exc, IdempotencyKeyConflictError):
        return problem_response(
            status=409, code="idempotency_key_conflict", title="Idempotency key conflict",
            detail="The idempotency key was already used with a different request body.",
        )
    if isinstance(exc, StaleResourceVersionError):
        return problem_response(
            status=409, code="stale_resource_version", title="Stale resource version",
            detail=f"Expected resource version {exc.expected}; current resource version is {exc.current}.",
        )
    if isinstance(exc, StaleProposalError):
        return problem_response(
            status=409, code="stale_proposal", title="Proposal is stale",
            detail="The proposal's expected scenario version is no longer current.",
        )
    if isinstance(exc, RejectedProposalError):
        return problem_response(
            status=409, code="proposal_rejected", title="Proposal is rejected",
            detail="The rejected proposal cannot accept this command.",
        )
    if isinstance(exc, ProjectionUnavailableError):
        return problem_response(
            status=503, code="scenario_projection_unavailable",
            title="Scenario projection unavailable",
            detail="The proposal exists but its scenario could not be read. Try again shortly.",
        )
    return problem_response(
        status=422, code="invalid_proposal_command", title="Invalid proposal command",
        detail=str(exc) or "The proposal command could not be validated.",
    )


@router.get("/{proposal_id}", response_model=ProposalOut, responses=_PROBLEMS)
def read_proposal(
    proposal_id: UUID,
    connection: Connection = Depends(get_site_context),
    repository: ProposalRepository = Depends(get_proposal_repository),
    projection_reader: ScenarioProjectionReader = Depends(get_projection_reader),
):
    try:
        value = get_proposal(repository, projection_reader, connection, proposal_id=proposal_id)
    except ProposalCommandError as exc:
        return _command_problem(exc)
    if value is None:
        return _not_found()
    return _out(value)


@router.post("/{proposal_id}/revisions", response_model=ProposalOut, responses=_PROBLEMS)
def revise(
    proposal_id: UUID,
    body: ProposalRevisionIn,
    idempotency_key: IdempotencyKey,
    connection: Connection = Depends(get_site_context),
    session: ResolvedSession = Depends(get_session),
    repository: ProposalRepository = Depends(get_proposal_repository),
    projection_reader: ScenarioProjectionReader = Depends(get_projection_reader),
):
    try:
        value = revise_proposal(
            repository, projection_reader, connection, proposal_id=proposal_id,
            site_id=session.site_id, actor_id=session.app_user_id,
            constraints=tuple(body.constraints),
            expected_resource_version=body.expected_resource_version,
            idempotency_key=idempotency_key,
        )
    except ProposalCommandError as exc:
        return _command_problem(exc)
    if value is None:
        return _not_found()
    return _out(value)


@router.post("/{proposal_id}/rejection", response_model=ProposalOut, responses=_PROBLEMS)
def reject(
    proposal_id: UUID,
    body: ProposalRejectionIn,
    idempotency_key: IdempotencyKey,
    connection: Connection = Depends(get_site_context),
    session: ResolvedSession = Depends(get_session),
    repository: ProposalRepository = Depends(get_proposal_repository),
    projection_reader: ScenarioProjectionReader = Depends(get_projection_reader),
):
    try:
        value = reject_proposal(
            repository, projection_reader, connection, proposal_id=proposal_id,
            site_id=session.site_id, actor_id=session.app_user_id,
            expected_resource_version=body.expected_resource_version,
            idempotency_key=idempotency_key,
        )
    except ProposalCommandError as exc:
        return _command_problem(exc)
    if value is None:
        return _not_found()
    return _out(value)
