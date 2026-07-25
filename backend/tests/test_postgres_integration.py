"""Live PostgreSQL proofs for migration, RLS, and the Gate A cutover."""
from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from adapters.postgres.fixture_history import PostgresFixtureHistoryAdapter
from adapters.postgres.schema import organization, scenario_version, site
from scripts.gate_a_cutover import FixtureSpec, REPO_ROOT, run_cutover
from services import run_service
from settings import default_settings


EXPECTED_TABLES = {
    "organization",
    "site",
    "scenario",
    "scenario_version",
    "fixture_lineage",
    "evidence_reference",
}


@pytest.fixture(scope="module")
def postgres_engine(governed_postgres_engine):
    return governed_postgres_engine


@pytest.mark.postgres
def test_migration_upgrade_and_downgrade_round_trip_on_fresh_database(
    fresh_postgres_database_url: str,
) -> None:
    alembic_config = Config(str(REPO_ROOT / "alembic.ini"))
    engine = create_engine(fresh_postgres_database_url)

    with engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
    assert EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names()))

    with engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.downgrade(alembic_config, "base")
    assert EXPECTED_TABLES.isdisjoint(set(inspect(engine).get_table_names()))
    engine.dispose()


@pytest.mark.postgres
def test_transaction_local_site_scope_hides_and_rejects_cross_site_rows(
    postgres_engine,
) -> None:
    adapter = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=postgres_engine,
    )
    suffix = uuid4().hex
    site_a = adapter.ensure_seed_site(f"Organization A {suffix}", f"Site A {suffix}")
    site_b = adapter.ensure_seed_site(f"Organization B {suffix}", f"Site B {suffix}")
    version_a = adapter.import_fixture(
        site_id=site_a,
        fixture_id=f"fixture-a-{suffix}",
        version="v1",
        payload={"site": "a"},
        source_package="tests",
        source_path="a.json",
    )
    version_b = adapter.import_fixture(
        site_id=site_b,
        fixture_id=f"fixture-b-{suffix}",
        version="v1",
        payload={"site": "b"},
        source_package="tests",
        source_path="b.json",
    )

    with postgres_engine.begin() as connection:
        connection.execute(
            text("SELECT set_config('app.site_id', :site_id, true)"),
            {"site_id": str(site_a)},
        )
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        visible_ids = set(
            connection.execute(select(scenario_version.c.id)).scalars()
        )
    assert version_a.scenario_version_id in visible_ids
    assert version_b.scenario_version_id not in visible_ids

    with postgres_engine.connect() as connection:
        site_b_scenario_id = connection.execute(
            select(scenario_version.c.scenario_id).where(
                scenario_version.c.id == version_b.scenario_version_id
            )
        ).scalar_one()

    with pytest.raises(DBAPIError):
        with postgres_engine.begin() as connection:
            connection.execute(
                text("SELECT set_config('app.site_id', :site_id, true)"),
                {"site_id": str(site_a)},
            )
            connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
            connection.execute(
                scenario_version.insert().values(
                    site_id=site_b,
                    scenario_id=site_b_scenario_id,
                    fixture_id=f"cross-site-{suffix}",
                    version="v1",
                    payload={"forbidden": True},
                    checksum_algorithm="sha256",
                    checksum_schema_version="rfc8785-v1",
                    checksum_digest="b" * 64,
                )
            )

    with postgres_engine.connect() as connection:
        assert (
            connection.execute(
                select(scenario_version.c.id).where(
                    scenario_version.c.fixture_id == f"cross-site-{suffix}"
                )
            ).one_or_none()
            is None
        )


@pytest.mark.postgres
def test_cutover_snapshots_throwaway_sqlite_and_imports_both_real_fixtures(
    postgres_engine,
    tmp_path: Path,
    monkeypatch,
) -> None:
    legacy_db = tmp_path / "legacy.db"
    with sqlite3.connect(legacy_db) as connection:
        connection.execute("CREATE TABLE scenarios (id TEXT PRIMARY KEY)")
        connection.execute("CREATE TABLE runs (id TEXT PRIMARY KEY)")
        connection.execute("INSERT INTO scenarios VALUES ('legacy-only')")

    suffix = uuid4().hex
    fixtures = (
        FixtureSpec(
            REPO_ROOT / "data" / "sample_tiny_input.json",
            f"sample_tiny_input-{suffix}",
            "v1",
        ),
        FixtureSpec(
            REPO_ROOT / "data" / "sample_tiny_input_more_tm.json",
            f"sample_tiny_input_more_tm-{suffix}",
            "v1",
        ),
    )
    settings = replace(
        default_settings(),
        db_path=str(legacy_db),
        database_url=postgres_engine.url.render_as_string(hide_password=False),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )
    pool = ThreadPoolExecutor(max_workers=1)
    pool.submit(lambda: None).result()
    monkeypatch.setattr(run_service, "_pool", pool)

    result = run_cutover(settings=settings, fixtures=fixtures)

    assert result.worker_drained is True
    assert run_service._pool is None
    assert result.snapshot_path.exists()
    with sqlite3.connect(result.snapshot_path) as snapshot:
        assert snapshot.execute("SELECT id FROM scenarios").fetchone()[0] == "legacy-only"
    with postgres_engine.connect() as connection:
        imported = connection.execute(
            select(
                scenario_version.c.fixture_id,
                scenario_version.c.payload,
                scenario_version.c.checksum_algorithm,
                scenario_version.c.checksum_schema_version,
                scenario_version.c.checksum_digest,
            ).where(
                scenario_version.c.site_id == result.site_id,
                scenario_version.c.fixture_id.in_(
                    [fixture.fixture_id for fixture in fixtures]
                ),
            )
        ).all()
    assert len(imported) == 2
    assert {row.fixture_id for row in imported} == {
        fixture.fixture_id for fixture in fixtures
    }
    assert all(row.checksum_algorithm == "sha256" for row in imported)
    assert all(row.checksum_schema_version == "rfc8785-v1" for row in imported)
    assert all(len(row.checksum_digest) == 64 for row in imported)
    expected_payloads = {
        fixture.fixture_id: json.loads(fixture.path.read_text(encoding="utf-8"))
        for fixture in fixtures
    }
    assert {row.fixture_id: row.payload for row in imported} == expected_payloads


@pytest.mark.postgres
def test_ensure_seed_site_is_race_safe_under_concurrent_calls(
    postgres_engine,
) -> None:
    adapter = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=postgres_engine,
    )
    suffix = uuid4().hex
    organization_name = f"Race Organization {suffix}"
    site_name = f"Race Site {suffix}"

    with ThreadPoolExecutor(max_workers=8) as executor:
        site_ids = list(
            executor.map(
                lambda _: adapter.ensure_seed_site(organization_name, site_name),
                range(8),
            )
        )

    assert len(set(site_ids)) == 1
    with postgres_engine.connect() as connection:
        organization_count = connection.execute(
            select(func.count())
            .select_from(organization)
            .where(organization.c.name == organization_name)
        ).scalar_one()
        site_count = connection.execute(
            select(func.count()).select_from(site).where(site.c.name == site_name)
        ).scalar_one()
    assert organization_count == 1
    assert site_count == 1


@pytest.mark.postgres
def test_temporary_database_cleanup_warns_on_drop_failure(monkeypatch) -> None:
    """Regression test for the review finding that swallowed DROP DATABASE
    failures silently, hiding leaked throwaway test databases."""
    import conftest as conftest_module
    from sqlalchemy.engine import Connection, make_url
    from sqlalchemy.exc import OperationalError

    original_exec_driver_sql = Connection.exec_driver_sql

    def _failing_exec_driver_sql(self, statement, *args, **kwargs):
        if statement.strip().upper().startswith("DROP DATABASE"):
            raise OperationalError(statement, {}, Exception("simulated failure"))
        return original_exec_driver_sql(self, statement, *args, **kwargs)

    monkeypatch.setattr(Connection, "exec_driver_sql", _failing_exec_driver_sql)

    leaked_database_url = None
    with pytest.warns(UserWarning, match="Failed to drop throwaway test database"):
        with conftest_module._temporary_postgres_database() as database_url:
            leaked_database_url = database_url

    # Clean up the deliberately-leaked database with the real (unpatched) driver.
    monkeypatch.undo()
    leaked_database_name = make_url(leaked_database_url).database
    admin_engine = create_engine(
        make_url(leaked_database_url).set(database="postgres"),
        isolation_level="AUTOCOMMIT",
    )
    try:
        with admin_engine.connect() as connection:
            connection.exec_driver_sql(
                f'DROP DATABASE IF EXISTS "{leaked_database_name}" WITH (FORCE)'
            )
    finally:
        admin_engine.dispose()
