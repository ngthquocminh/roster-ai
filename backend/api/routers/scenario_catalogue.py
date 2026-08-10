"""Versioned read-only scenario catalogue endpoints."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import Connection

from api.deps import get_catalogue_reader, get_site_context
from api.schemas import (
    FixtureCatalogueEntryOut,
    ProblemDetailsV1,
    ScenarioContextOut,
)
from application.ports.scenario_catalogue import (
    FixtureCatalogueEntry,
    ScenarioCatalogueReader,
    ScenarioContext,
)


router = APIRouter(prefix="/scenarios", tags=["scenario catalogue"])


# Fields are mapped one by one rather than splatted from `vars()`: Pydantic
# ignores unknown keys, so a field added to the port dataclass and wired
# through the adapter would silently never reach the wire.
def _catalogue_entry_out(
    entry: FixtureCatalogueEntry,
) -> FixtureCatalogueEntryOut:
    return FixtureCatalogueEntryOut(
        scenario_id=entry.scenario_id,
        fixture_id=entry.fixture_id,
        scenario_name=entry.scenario_name,
        scenario_version_id=entry.scenario_version_id,
        fixture_version=entry.fixture_version,
        checksum_algorithm=entry.checksum_algorithm,
        checksum_schema_version=entry.checksum_schema_version,
        checksum_digest=entry.checksum_digest,
        imported_at=entry.imported_at,
        site_id=entry.site_id,
    )


def _scenario_context_out(context: ScenarioContext) -> ScenarioContextOut:
    return ScenarioContextOut(
        scenario_name=context.scenario_name,
        scenario_id=context.scenario_id,
        scenario_version_id=context.scenario_version_id,
        fixture_version=context.fixture_version,
        checksum_algorithm=context.checksum_algorithm,
        checksum_schema_version=context.checksum_schema_version,
        checksum_digest=context.checksum_digest,
        site_id=context.site_id,
        baseline_schedule_version=context.baseline_schedule_version,
    )


@router.get(
    "",
    response_model=list[FixtureCatalogueEntryOut],
    responses={401: {"model": ProblemDetailsV1}},
)
def list_fixture_versions(
    connection: Connection = Depends(get_site_context),
    reader: ScenarioCatalogueReader = Depends(get_catalogue_reader),
) -> list[FixtureCatalogueEntryOut]:
    return [
        _catalogue_entry_out(entry)
        for entry in reader.list_fixture_versions(connection)
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
    reader: ScenarioCatalogueReader = Depends(get_catalogue_reader),
) -> ScenarioContextOut:
    context = reader.get_scenario_context(connection, scenario_id)
    if context is None:
        raise HTTPException(status_code=404)
    return _scenario_context_out(context)
