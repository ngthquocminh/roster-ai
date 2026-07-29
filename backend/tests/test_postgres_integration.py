"""Live PostgreSQL proofs for migration, RLS, and the Gate A cutover."""
from __future__ import annotations

import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, inspect, select, text
from sqlalchemy.exc import DBAPIError

from adapters.postgres.fixture_history import PostgresFixtureHistoryAdapter
from adapters.postgres.schema import (
    app_user,
    membership,
    organization,
    scenario_version,
    session_index,
    site,
)
from api.auth_security import SESSION_COOKIE_NAME
from api.deps import (
    _site_context_engine,
    get_identity_store,
    get_settings,
    get_site_context,
)
from api.main import app
from application.ports.session import ResolvedSession
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
    "app_user",
    "membership",
}


@pytest.fixture(scope="module")
def postgres_engine(governed_postgres_engine):
    return governed_postgres_engine


class _ResolvedIdentityStore:
    def __init__(self, session: ResolvedSession) -> None:
        self._session = session

    def resolve_session(self, _token_hash: str) -> ResolvedSession:
        return self._session


@contextmanager
def _catalogue_client(postgres_engine, *, site_id, tmp_path):
    restricted_url = postgres_engine.url.set(
        username="shiftmind_login",
        password="shiftmind_login",
    ).render_as_string(hide_password=False)
    settings = replace(
        default_settings(),
        database_url=restricted_url,
        provisioning_database_url=postgres_engine.url.render_as_string(
            hide_password=False
        ),
        db_path=str(tmp_path / "legacy.db"),
        maintenance_flag_path=str(tmp_path / "gate-a-maintenance"),
    )
    session = ResolvedSession(
        app_user_id=uuid4(),
        site_id=site_id,
        csrf_token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
    )
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_identity_store] = lambda: (
        _ResolvedIdentityStore(session)
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


@pytest.fixture()
def catalogue_site_rows(postgres_engine):
    adapter = PostgresFixtureHistoryAdapter(
        default_settings().provisioning_database_url,
        engine=postgres_engine,
    )
    suffix = uuid4().hex
    site_a = adapter.ensure_seed_site(
        f"Catalogue Organization A {suffix}",
        f"Catalogue Site A {suffix}",
    )
    site_b = adapter.ensure_seed_site(
        f"Catalogue Organization B {suffix}",
        f"Catalogue Site B {suffix}",
    )
    imports_a = (
        adapter.import_fixture(
            site_id=site_a,
            fixture_id=f"fixture-z-{suffix}",
            version="v1",
            payload={"fixture": "z"},
            source_package="tests",
            source_path="z.json",
        ),
        adapter.import_fixture(
            site_id=site_a,
            fixture_id=f"fixture-a-{suffix}",
            version="v2",
            payload={"fixture": "a", "version": 2},
            source_package="tests",
            source_path="a-v2.json",
        ),
        adapter.import_fixture(
            site_id=site_a,
            fixture_id=f"fixture-a-{suffix}",
            version="v1",
            payload={"fixture": "a", "version": 1},
            source_package="tests",
            source_path="a-v1.json",
        ),
        # Double digits: under a text sort "v10" lands between "v1" and "v2"
        # and loses the latest-version race to "v9". This row is what makes
        # the numeric ordering key observable.
        adapter.import_fixture(
            site_id=site_a,
            fixture_id=f"fixture-a-{suffix}",
            version="v10",
            payload={"fixture": "a", "version": 10},
            source_package="tests",
            source_path="a-v10.json",
        ),
    )
    import_b = adapter.import_fixture(
        site_id=site_b,
        fixture_id=f"fixture-b-{suffix}",
        version="v1",
        payload={"fixture": "b"},
        source_package="tests",
        source_path="b.json",
    )
    with postgres_engine.connect() as connection:
        rows = connection.execute(
            select(
                scenario_version.c.id,
                scenario_version.c.scenario_id,
                scenario_version.c.site_id,
                scenario_version.c.fixture_id,
                scenario_version.c.version,
                scenario_version.c.checksum_digest,
            )
            .where(scenario_version.c.site_id.in_((site_a, site_b)))
            .order_by(scenario_version.c.id)
        ).all()
    return {
        "site_a": site_a,
        "site_b": site_b,
        "imports_a": imports_a,
        "import_b": import_b,
        "rows": rows,
    }


def _version_order_key(row) -> tuple[int, int, str, str]:
    """Mirror the adapter's ordering key: digits-as-number, then raw text, then
    the stable id. Rows carrying no digit sort last (NULLS LAST)."""
    digits = "".join(char for char in row.version if char.isdigit())
    return (
        (0, int(digits)) if digits else (1, 0)
    ) + (row.version, str(row.id))


def _catalogue_order_key(row) -> tuple:
    return (row.fixture_id,) + _version_order_key(row)


@pytest.mark.postgres
def test_catalogue_api_is_ordered_complete_and_read_only(
    postgres_engine,
    catalogue_site_rows,
    tmp_path,
) -> None:
    site_a = catalogue_site_rows["site_a"]
    rows_a = [
        row for row in catalogue_site_rows["rows"] if row.site_id == site_a
    ]
    before = [
        (row.id, row.checksum_digest)
        for row in catalogue_site_rows["rows"]
    ]

    with _catalogue_client(
        postgres_engine,
        site_id=site_a,
        tmp_path=tmp_path,
    ) as client:
        response = client.get(
            "/api/v1/scenarios",
            headers={"Cookie": f"{SESSION_COOKIE_NAME}=site-a-session"},
        )
        assert response.status_code == 200
        body = response.json()
        assert len(body) == len(rows_a)
        # Expected order mirrors the adapter's documented key: fixture id, then
        # the version's digits read as a number, then the raw text, then the
        # stable id. A plain Python sort() would expect the old text ordering
        # and put v10 ahead of v2.
        assert [
            (entry["fixture_id"], entry["fixture_version"], entry["scenario_version_id"])
            for entry in body
        ] == [
            (row.fixture_id, row.version, str(row.id))
            for row in sorted(rows_a, key=_catalogue_order_key)
        ]
        # Guard the guard: without a double-digit version this proves nothing.
        assert "v10" in {row.version for row in rows_a}
        assert {entry["scenario_id"] for entry in body} == {
            str(row.scenario_id) for row in rows_a
        }
        assert all(
            entry["checksum_algorithm"] == "sha256"
            and entry["checksum_schema_version"] == "rfc8785-v1"
            and len(entry["checksum_digest"]) == 64
            for entry in body
        )
        # The documented resolution is ORDER BY version DESC, id DESC LIMIT 1,
        # so the governed version of a multi-version fixture is the last one
        # under the same ascending order the catalogue lists by.
        expected_latest: dict[str, str] = {}
        for row in sorted(rows_a, key=_version_order_key):
            expected_latest[str(row.scenario_id)] = row.version
        # The multi-version fixture must resolve to v10, not v9-style text max.
        assert "v10" in expected_latest.values()
        # Guard the guard: this proof is only meaningful while the fixture
        # data actually contains a scenario with more than one version.
        assert max(
            sum(1 for row in rows_a if str(row.scenario_id) == scenario_id)
            for scenario_id in expected_latest
        ) > 1

        for scenario_id in {entry["scenario_id"] for entry in body}:
            detail = client.get(
                f"/api/v1/scenarios/{scenario_id}",
                headers={"Cookie": f"{SESSION_COOKIE_NAME}=site-a-session"},
            )
            assert detail.status_code == 200
            assert (
                detail.json()["fixture_version"] == expected_latest[scenario_id]
            )

    with postgres_engine.connect() as connection:
        after = connection.execute(
            select(
                scenario_version.c.id,
                scenario_version.c.checksum_digest,
            )
            .where(scenario_version.c.site_id.in_(
                (
                    catalogue_site_rows["site_a"],
                    catalogue_site_rows["site_b"],
                )
            ))
            .order_by(scenario_version.c.id)
        ).all()
    assert [(row.id, row.checksum_digest) for row in after] == before


@pytest.mark.postgres
def test_catalogue_api_hides_cross_site_rows_like_unknown_rows(
    postgres_engine,
    catalogue_site_rows,
    tmp_path,
) -> None:
    site_a = catalogue_site_rows["site_a"]
    site_b_version = catalogue_site_rows["import_b"]
    with postgres_engine.connect() as connection:
        site_b_scenario_id = connection.execute(
            select(scenario_version.c.scenario_id).where(
                scenario_version.c.site_id == catalogue_site_rows["site_b"],
                scenario_version.c.id == site_b_version.scenario_version_id,
            )
        ).scalar_one()

    with _catalogue_client(
        postgres_engine,
        site_id=site_a,
        tmp_path=tmp_path,
    ) as client:
        headers = {"Cookie": f"{SESSION_COOKIE_NAME}=site-a-session"}
        catalogue = client.get("/api/v1/scenarios", headers=headers)
        foreign = client.get(
            f"/api/v1/scenarios/{site_b_scenario_id}",
            headers=headers,
        )
        unknown = client.get(
            f"/api/v1/scenarios/{uuid4()}",
            headers=headers,
        )

    assert catalogue.status_code == 200
    assert str(site_b_version.scenario_version_id) not in {
        entry["scenario_version_id"] for entry in catalogue.json()
    }
    assert foreign.status_code == 404
    assert unknown.status_code == 404
    assert foreign.content == unknown.content


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
    assert {"session_index", "login_handshake"} == set(
        inspect(engine).get_table_names(schema="auth")
    )
    with engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.check(alembic_config)

    with engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.downgrade(alembic_config, "base")
    assert EXPECTED_TABLES.isdisjoint(set(inspect(engine).get_table_names()))
    with engine.begin() as connection:
        alembic_config.attributes["connection"] = connection
        command.upgrade(alembic_config, "head")
    assert EXPECTED_TABLES.issubset(set(inspect(engine).get_table_names()))
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
    organization_name = f"Shared Organization {suffix}"
    site_a = adapter.ensure_seed_site(organization_name, f"Site A {suffix}")
    site_b = adapter.ensure_seed_site(organization_name, f"Site B {suffix}")
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
def test_internal_auth_tables_and_resolver_follow_ad23_privileges(
    postgres_engine,
) -> None:
    with postgres_engine.connect() as connection:
        table_privileges = connection.execute(
            text(
                "SELECT "
                "has_table_privilege('shiftmind_runtime', "
                "'auth.session_index', 'SELECT') AS session_select, "
                "has_table_privilege('shiftmind_runtime', "
                "'auth.login_handshake', 'SELECT') AS handshake_select"
            )
        ).one()
        function = connection.execute(
            text(
                "SELECT p.prosecdef, p.proconfig, "
                "has_function_privilege("
                "'shiftmind_runtime', p.oid, 'EXECUTE') AS runtime_execute, "
                "EXISTS ("
                "  SELECT 1 FROM aclexplode(p.proacl) AS acl "
                "  WHERE acl.grantee = 0 AND acl.privilege_type = 'EXECUTE'"
                ") AS public_execute "
                "FROM pg_proc AS p "
                "JOIN pg_namespace AS n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'auth' AND p.proname = 'resolve_session'"
            )
        ).one()

    assert table_privileges.session_select is False
    assert table_privileges.handshake_select is False
    assert function.prosecdef is True
    assert function.runtime_execute is True
    assert function.public_execute is False
    assert "search_path=auth, pg_catalog" in function.proconfig


@pytest.mark.postgres
def test_resolve_session_rechecks_current_membership_on_every_request(
    postgres_engine,
) -> None:
    suffix = uuid4().hex
    site_id = PostgresFixtureHistoryAdapter(
        default_settings().database_url,
        engine=postgres_engine,
    ).ensure_seed_site(
        f"Session Organization {suffix}",
        f"Session Site {suffix}",
    )
    session_token_hash = "a" * 64
    with postgres_engine.begin() as connection:
        app_user_id = connection.execute(
            app_user.insert()
            .values(
                idp_subject=f"session-planner-{suffix}",
                email=f"session-{suffix}@example.test",
            )
            .returning(app_user.c.id)
        ).scalar_one()
        membership_id = connection.execute(
            membership.insert()
            .values(app_user_id=app_user_id, site_id=site_id)
            .returning(membership.c.id)
        ).scalar_one()
        connection.execute(
            session_index.insert().values(
                session_token_hash=session_token_hash,
                csrf_token_hash="b" * 64,
                app_user_id=app_user_id,
                site_id=site_id,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
            )
        )

    with postgres_engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        resolved = connection.execute(
            text(
                "SELECT app_user_id, site_id "
                "FROM auth.resolve_session(:token_hash)"
            ),
            {"token_hash": session_token_hash},
        ).one()
    assert resolved.app_user_id == app_user_id
    assert resolved.site_id == site_id

    with postgres_engine.begin() as connection:
        connection.execute(
            membership.update()
            .where(membership.c.id == membership_id)
            .values(revoked_at=func.now())
        )
    with postgres_engine.begin() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        assert connection.execute(
            text(
                "SELECT app_user_id "
                "FROM auth.resolve_session(:token_hash)"
            ),
            {"token_hash": session_token_hash},
        ).one_or_none() is None


@pytest.mark.postgres
def test_site_context_dependency_uses_only_the_resolved_session_site(
    postgres_engine,
) -> None:
    session_site_id = uuid4()
    settings = replace(
        default_settings(),
        database_url=postgres_engine.url.render_as_string(hide_password=False),
    )
    session = ResolvedSession(
        app_user_id=uuid4(),
        site_id=session_site_id,
        csrf_token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc),
    )

    context = get_site_context(session=session, settings=settings)
    connection = next(context)
    assert connection.execute(
        text("SELECT current_setting('app.site_id', true)")
    ).scalar_one() == str(session_site_id)
    assert connection.execute(text("SELECT current_user")).scalar_one() == (
        "shiftmind_runtime"
    )
    context.close()

    engine = _site_context_engine(settings.database_url)
    with engine.connect() as fresh_connection:
        assert fresh_connection.execute(
            text("SELECT current_setting('app.site_id', true)")
        ).scalar_one() in (None, "")


@pytest.mark.postgres
def test_site_context_cleanup_does_not_mask_the_original_error(
    postgres_engine,
) -> None:
    """Regression test for the review finding that the app.site_id reset in
    get_site_context's `finally` could itself raise InFailedSqlTransaction
    on an already-aborted transaction, hiding the real downstream error."""
    settings = replace(
        default_settings(),
        database_url=postgres_engine.url.render_as_string(hide_password=False),
    )
    session = ResolvedSession(
        app_user_id=uuid4(),
        site_id=uuid4(),
        csrf_token_hash="a" * 64,
        expires_at=datetime.now(timezone.utc),
    )
    context = get_site_context(session=session, settings=settings)
    connection = next(context)
    with pytest.raises(DBAPIError):
        connection.execute(text("SELECT 1/0"))  # aborts the PG transaction

    class _DownstreamFailure(Exception):
        pass

    with pytest.raises(_DownstreamFailure):
        context.throw(_DownstreamFailure("simulated downstream failure"))


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
        provisioning_database_url=postgres_engine.url.render_as_string(
            hide_password=False
        ),
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
