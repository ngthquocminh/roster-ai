"""Application read port for immutable, site-governed fixture metadata."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Connection


@dataclass(frozen=True)
class FixtureCatalogueEntry:
    scenario_id: UUID
    fixture_id: str
    scenario_name: str
    scenario_version_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    imported_at: datetime
    site_id: UUID


@dataclass(frozen=True)
class ScenarioContext:
    scenario_name: str
    scenario_id: UUID
    # The identity of the version this context describes. Callers that pin a
    # version (AD-9) must select by this id rather than re-deriving "latest"
    # themselves: this reader orders by version ordinal, so any second
    # resolution rule would silently disagree with what the planner is shown.
    scenario_version_id: UUID
    fixture_version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    site_id: UUID
    baseline_schedule_version: str | None


class ScenarioCatalogueReader(Protocol):
    def list_fixture_versions(
        self,
        connection: Connection,
    ) -> tuple[FixtureCatalogueEntry, ...]: ...

    def get_scenario_context(
        self,
        connection: Connection,
        scenario_id: UUID,
    ) -> ScenarioContext | None: ...
