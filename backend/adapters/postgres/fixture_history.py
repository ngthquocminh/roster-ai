"""PostgreSQL writes for predefined fixture history."""
from __future__ import annotations

import hashlib
import struct
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, create_engine, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import IntegrityError

from application.contracts.canonical import canonicalize_json
from adapters.postgres.schema import (
    fixture_lineage,
    organization,
    scenario,
    scenario_version,
    site,
)

CHECKSUM_ALGORITHM = "sha256"
CHECKSUM_SCHEMA_VERSION = "rfc8785-v1"


class FixtureVersionConflictError(ValueError):
    """The fixture version exists with a different canonical payload."""


@dataclass(frozen=True)
class FixtureImportResult:
    """Stable semantic result returned by a fixture import."""

    scenario_version_id: UUID
    site_id: UUID
    fixture_id: str
    version: str
    checksum_algorithm: str
    checksum_schema_version: str
    checksum_digest: str
    created: bool


class PostgresFixtureHistoryAdapter:
    """Create site-owned scenario versions without touching legacy SQLite."""

    def __init__(
        self,
        database_url: str,
        *,
        engine: Engine | None = None,
    ) -> None:
        self._engine = engine or create_engine(database_url)

    def ensure_seed_site(
        self,
        organization_name: str,
        site_name: str,
    ) -> UUID:
        """Return the maintenance import site, creating it on first cutover.

        Serialized with a transaction-scoped advisory lock keyed on the given
        names rather than a schema-level uniqueness constraint on
        organization/site display names — this story's only caller passes two
        fixed literal names, and a global name-uniqueness rule is a separate
        domain decision this story doesn't make.
        """
        lock_key = struct.unpack(
            ">q",
            hashlib.sha256(
                f"{organization_name}\x1e{site_name}".encode("utf-8")
            ).digest()[:8],
        )[0]
        with self._engine.begin() as connection:
            connection.execute(select(func.pg_advisory_xact_lock(lock_key)))
            organization_id = connection.execute(
                select(organization.c.id)
                .where(organization.c.name == organization_name)
                .order_by(organization.c.id)
                .limit(1)
            ).scalar_one_or_none()
            if organization_id is None:
                organization_id = connection.execute(
                    organization.insert()
                    .values(name=organization_name)
                    .returning(organization.c.id)
                ).scalar_one()

            site_id = connection.execute(
                select(site.c.id)
                .where(
                    site.c.organization_id == organization_id,
                    site.c.name == site_name,
                )
                .order_by(site.c.id)
                .limit(1)
            ).scalar_one_or_none()
            if site_id is None:
                site_id = connection.execute(
                    site.insert()
                    .values(
                        organization_id=organization_id,
                        name=site_name,
                    )
                    .returning(site.c.id)
                ).scalar_one()
            return site_id

    def import_fixture(
        self,
        *,
        site_id: UUID,
        fixture_id: str,
        version: str,
        payload: Any,
        source_package: str,
        source_path: str,
    ) -> FixtureImportResult:
        """Insert or replay one immutable, canonically checksummed fixture."""
        canonical_bytes = canonicalize_json(payload)
        digest = hashlib.sha256(canonical_bytes).hexdigest()

        with self._engine.begin() as connection:
            scenario_id = connection.execute(
                insert(scenario)
                .values(
                    site_id=site_id,
                    fixture_id=fixture_id,
                    name=fixture_id,
                )
                .on_conflict_do_nothing(
                    index_elements=[scenario.c.site_id, scenario.c.fixture_id],
                )
                .returning(scenario.c.id)
            ).scalar_one_or_none()
            if scenario_id is None:
                scenario_id = connection.execute(
                    select(scenario.c.id).where(
                        scenario.c.site_id == site_id,
                        scenario.c.fixture_id == fixture_id,
                    )
                ).scalar_one()

            existing = self._find_version(
                connection,
                site_id=site_id,
                fixture_id=fixture_id,
                version=version,
            )
            if existing is not None:
                return self._replay_or_reject(existing, digest)

            try:
                with connection.begin_nested():
                    row = connection.execute(
                        scenario_version.insert()
                        .values(
                            site_id=site_id,
                            scenario_id=scenario_id,
                            fixture_id=fixture_id,
                            version=version,
                            payload=payload,
                            checksum_algorithm=CHECKSUM_ALGORITHM,
                            checksum_schema_version=CHECKSUM_SCHEMA_VERSION,
                            checksum_digest=digest,
                        )
                        .returning(*self._result_columns())
                    ).one()
            except IntegrityError:
                existing = self._find_version(
                    connection,
                    site_id=site_id,
                    fixture_id=fixture_id,
                    version=version,
                )
                if existing is None:
                    raise
                return self._replay_or_reject(existing, digest)

            connection.execute(
                fixture_lineage.insert().values(
                    site_id=site_id,
                    scenario_version_id=row.id,
                    source_package=source_package,
                    source_path=source_path,
                )
            )

        return self._to_result(row, created=True)

    @staticmethod
    def _result_columns() -> tuple:
        return (
            scenario_version.c.id,
            scenario_version.c.site_id,
            scenario_version.c.fixture_id,
            scenario_version.c.version,
            scenario_version.c.checksum_algorithm,
            scenario_version.c.checksum_schema_version,
            scenario_version.c.checksum_digest,
        )

    @classmethod
    def _find_version(
        cls,
        connection,
        *,
        site_id: UUID,
        fixture_id: str,
        version: str,
    ):
        return connection.execute(
            select(*cls._result_columns()).where(
                scenario_version.c.site_id == site_id,
                scenario_version.c.fixture_id == fixture_id,
                scenario_version.c.version == version,
            )
        ).one_or_none()

    @classmethod
    def _replay_or_reject(
        cls,
        existing,
        digest: str,
    ) -> FixtureImportResult:
        if existing.checksum_digest != digest:
            raise FixtureVersionConflictError(
                "Fixture version already exists with a different checksum"
            )
        return cls._to_result(existing, created=False)

    @staticmethod
    def _to_result(row, *, created: bool) -> FixtureImportResult:
        return FixtureImportResult(
            scenario_version_id=row.id,
            site_id=row.site_id,
            fixture_id=row.fixture_id,
            version=row.version,
            checksum_algorithm=row.checksum_algorithm,
            checksum_schema_version=row.checksum_schema_version,
            checksum_digest=row.checksum_digest,
            created=created,
        )
