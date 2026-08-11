"""Unit contract tests for the governed scenario catalogue read adapter."""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

from sqlalchemy.dialects import postgresql

from adapters.postgres.scenario_catalogue import PostgresScenarioCatalogueReader
from application.ports.scenario_catalogue import (
    FixtureCatalogueEntry,
    ScenarioContext,
)


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows

    def one_or_none(self):
        return self._rows[0] if self._rows else None


class _Connection:
    def __init__(self, rows):
        self._rows = rows
        self.statements = []

    def execute(self, statement):
        self.statements.append(statement)
        return _Result(self._rows)


def _catalogue_row(
    *,
    fixture_id: str = "fixture-a",
    fixture_version: str = "v1",
):
    return SimpleNamespace(
        scenario_id=uuid4(),
        fixture_id=fixture_id,
        scenario_name="Fixture A",
        scenario_version_id=uuid4(),
        fixture_version=fixture_version,
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        imported_at=datetime(2026, 7, 24, tzinfo=timezone.utc),
        site_id=uuid4(),
    )


# The numeric sort key, as rendered with literal_binds. The backslash is
# doubled only by that inline rendering — real execution passes the pattern as
# a bind parameter, and the live PostgreSQL ordering proof in
# test_postgres_integration.py is what confirms the regex behaves.
_VERSION_ORDINAL_SQL = (
    "CAST(nullif(regexp_replace(scenario_version.version, '\\\\D', '', 'g'), '') "
    "AS NUMERIC)"
)


def _sql(statement) -> str:
    return " ".join(
        str(
            statement.compile(
                dialect=postgresql.dialect(),
                compile_kwargs={"literal_binds": True},
            )
        ).split()
    )


def test_list_fixture_versions_maps_frozen_entries_and_defines_stable_order() -> None:
    rows = [
        _catalogue_row(fixture_id="fixture-a", fixture_version="v1"),
        _catalogue_row(fixture_id="fixture-a", fixture_version="v2"),
    ]
    connection = _Connection(rows)

    entries = PostgresScenarioCatalogueReader().list_fixture_versions(connection)

    assert entries == tuple(FixtureCatalogueEntry(**vars(row)) for row in rows)
    assert FixtureCatalogueEntry.__dataclass_params__.frozen is True
    statement = _sql(connection.statements[0])
    # Ordering keys on the digits in the version, read as a number, so v10
    # sorts after v2 rather than before it; the raw text and the stable id
    # keep the order total for versions carrying no digits.
    assert (
        f"ORDER BY scenario.fixture_id, {_VERSION_ORDINAL_SQL} ASC NULLS LAST, "
        "scenario_version.version, scenario_version.id"
    ) in statement
    assert "WHERE scenario.site_id" not in statement
    assert "WHERE scenario_version.site_id" not in statement


def test_get_scenario_context_selects_governed_latest_version_without_site_input() -> None:
    row = _catalogue_row(fixture_version="v2")
    row.baseline_schedule_version = None
    connection = _Connection([row])

    context = PostgresScenarioCatalogueReader().get_scenario_context(
        connection,
        row.scenario_id,
    )

    assert context == ScenarioContext(
        scenario_name=row.scenario_name,
        scenario_id=row.scenario_id,
        scenario_version_id=row.scenario_version_id,
        fixture_version=row.fixture_version,
        checksum_algorithm=row.checksum_algorithm,
        checksum_schema_version=row.checksum_schema_version,
        checksum_digest=row.checksum_digest,
        site_id=row.site_id,
        baseline_schedule_version=None,
    )
    assert ScenarioContext.__dataclass_params__.frozen is True
    statement = _sql(connection.statements[0])
    assert f"scenario.id = '{row.scenario_id}'" in statement
    assert (
        f"ORDER BY {_VERSION_ORDINAL_SQL} DESC NULLS LAST, "
        "scenario_version.version DESC, scenario_version.id DESC"
    ) in statement
    assert "LIMIT 1" in statement
    where_clause = statement.split(" WHERE ", 1)[1].split(" ORDER BY", 1)[0]
    assert "site_id" not in where_clause


def test_get_scenario_context_returns_none_when_rls_hides_the_row() -> None:
    connection = _Connection([])

    assert (
        PostgresScenarioCatalogueReader().get_scenario_context(
            connection,
            UUID("00000000-0000-0000-0000-000000000001"),
        )
        is None
    )
