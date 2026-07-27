"""Versioned read-only scenario catalogue endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection

from adapters.postgres.scenario_catalogue import (
    PostgresScenarioCatalogueReader,
)
from api.deps import get_site_context
from api.schemas import (
    FixtureCatalogueEntryOut,
    ProblemDetailsV1,
    ScenarioContextOut,
)


router = APIRouter(prefix="/scenarios", tags=["scenario catalogue"])
_reader = PostgresScenarioCatalogueReader()


@router.get(
    "",
    response_model=list[FixtureCatalogueEntryOut],
    responses={401: {"model": ProblemDetailsV1}},
)
def list_fixture_versions(
    connection: Connection = Depends(get_site_context),
) -> list[FixtureCatalogueEntryOut]:
    return [
        FixtureCatalogueEntryOut(**vars(entry))
        for entry in _reader.list_fixture_versions(connection)
    ]


@router.get(
    "/{scenario_id}",
    response_model=ScenarioContextOut,
    responses={
        401: {"model": ProblemDetailsV1},
        404: {"model": ProblemDetailsV1},
    },
)
def get_scenario_context(
    scenario_id: UUID,
    connection: Connection = Depends(get_site_context),
) -> ScenarioContextOut:
    context = _reader.get_scenario_context(connection, scenario_id)
    if context is None:
        raise HTTPException(status_code=404)
    return ScenarioContextOut(**vars(context))
