"""PostgreSQL reads for immutable scenario catalogue metadata."""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import (
    Connection,
    Numeric,
    String,
    and_,
    cast,
    func,
    literal,
    nulls_last,
    select,
)

from adapters.postgres.schema import scenario, scenario_version
from application.ports.scenario_catalogue import (
    FixtureCatalogueEntry,
    ScenarioContext,
)


# `scenario_version.version` is a free-form String(100) with no format
# constraint, so ordering it as text puts "v10" before "v2" — which would make
# `get_scenario_context` publish v9 as the governed latest version of a fixture
# that has a v10, along with v9's checksum_digest. On a provenance endpoint that
# is a silent wrong answer, so ordering keys on the digits the string contains,
# read as a number.
#
# Supported format: one integer with an optional non-numeric prefix ("v1", "2",
# "rev-7"). Multi-part versions are ordered by their concatenated digits, which
# is correct for "1.2" vs "1.10" but not for "1.2" vs "11" — introducing dotted
# versions means revisiting this expression. Strings carrying no digit at all
# yield NULL and sort last rather than raising, so the ordering stays total for
# any input: (ordinal, raw text, stable id).
_VERSION_ORDINAL = cast(
    func.nullif(
        func.regexp_replace(scenario_version.c.version, r"\D", "", "g"),
        "",
    ),
    Numeric,
)


class PostgresScenarioCatalogueReader:
    """Read through an already-open, transaction-scoped connection."""

    @staticmethod
    def _scenario_version_join():
        return scenario.join(
            scenario_version,
            and_(
                scenario.c.id == scenario_version.c.scenario_id,
                scenario.c.site_id == scenario_version.c.site_id,
            ),
        )

    def list_fixture_versions(
        self,
        connection: Connection,
    ) -> tuple[FixtureCatalogueEntry, ...]:
        rows = connection.execute(
            select(
                scenario.c.id.label("scenario_id"),
                scenario.c.fixture_id,
                scenario.c.name.label("scenario_name"),
                scenario_version.c.id.label("scenario_version_id"),
                scenario_version.c.version.label("fixture_version"),
                scenario_version.c.checksum_algorithm,
                scenario_version.c.checksum_schema_version,
                scenario_version.c.checksum_digest,
                scenario_version.c.imported_at,
                scenario.c.site_id,
            )
            .select_from(self._scenario_version_join())
            .order_by(
                scenario.c.fixture_id,
                nulls_last(_VERSION_ORDINAL.asc()),
                scenario_version.c.version,
                scenario_version.c.id,
            )
        ).all()
        return tuple(
            FixtureCatalogueEntry(
                scenario_id=row.scenario_id,
                fixture_id=row.fixture_id,
                scenario_name=row.scenario_name,
                scenario_version_id=row.scenario_version_id,
                fixture_version=row.fixture_version,
                checksum_algorithm=row.checksum_algorithm,
                checksum_schema_version=row.checksum_schema_version,
                checksum_digest=row.checksum_digest,
                imported_at=row.imported_at,
                site_id=row.site_id,
            )
            for row in rows
        )

    def get_scenario_context(
        self,
        connection: Connection,
        scenario_id: UUID,
    ) -> ScenarioContext | None:
        row = connection.execute(
            select(
                scenario.c.name.label("scenario_name"),
                scenario.c.id.label("scenario_id"),
                scenario_version.c.id.label("scenario_version_id"),
                scenario_version.c.version.label("fixture_version"),
                scenario_version.c.checksum_algorithm,
                scenario_version.c.checksum_schema_version,
                scenario_version.c.checksum_digest,
                scenario.c.site_id,
                literal(None, type_=String).label(
                    "baseline_schedule_version"
                ),
            )
            .select_from(self._scenario_version_join())
            .where(scenario.c.id == scenario_id)
            .order_by(
                nulls_last(_VERSION_ORDINAL.desc()),
                scenario_version.c.version.desc(),
                scenario_version.c.id.desc(),
            )
            .limit(1)
        ).one_or_none()
        if row is None:
            return None
        return ScenarioContext(
            scenario_name=row.scenario_name,
            scenario_id=row.scenario_id,
            scenario_version_id=row.scenario_version_id,
            fixture_version=row.fixture_version,
            checksum_algorithm=row.checksum_algorithm,
            checksum_schema_version=row.checksum_schema_version,
            checksum_digest=row.checksum_digest,
            site_id=row.site_id,
            baseline_schedule_version=row.baseline_schedule_version,
        )
