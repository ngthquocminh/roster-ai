from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import CheckConstraint, text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.exc import IntegrityError

from adapters.postgres.schema import metadata


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION = (
    BACKEND_ROOT
    / "migrations"
    / "versions"
    / "f1a2b3c4d5e6_add_schedule_run_aggregate.py"
)


def _check_sql(table_name: str) -> set[str]:
    return {
        str(constraint.sqltext)
        for constraint in metadata.tables[table_name].constraints
        if isinstance(constraint, CheckConstraint)
    }


def test_schedule_run_metadata_contains_the_four_site_owned_tables() -> None:
    for table_name in (
        "run_snapshot",
        "schedule_run",
        "schedule_version",
        "schedule_assignment",
    ):
        table = metadata.tables[table_name]
        assert isinstance(table.c.id.type, UUID)
        assert isinstance(table.c.site_id.type, UUID)
        assert table.c.site_id.nullable is False

    assert isinstance(metadata.tables["run_snapshot"].c.payload.type, JSONB)
    assert isinstance(metadata.tables["schedule_version"].c.payload.type, JSONB)


def test_schedule_run_checks_closed_status_and_candidate_promotion() -> None:
    checks = _check_sql("schedule_run")
    assert any("solver_queued" in sql and "solver_failed" in sql for sql in checks)
    assert (
        "candidate_schedule_version_id IS NULL OR status = 'solver_completed'"
        in checks
    )


def test_schedule_aggregate_migration_enforces_rls_and_narrow_grants() -> None:
    migration = MIGRATION.read_text(encoding="utf-8")

    assert 'down_revision: str = "e9f0a1b2c3d4"' in migration
    for table_name in (
        "run_snapshot",
        "schedule_run",
        "schedule_version",
        "schedule_assignment",
    ):
        assert f'"{table_name}"' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "GRANT SELECT, INSERT ON {table} TO shiftmind_runtime" in migration
    assert "REVOKE UPDATE, DELETE ON {table} FROM shiftmind_runtime" in migration
    assert (
        "GRANT UPDATE (status, reason, candidate_schedule_version_id, finished_at) "
        "ON schedule_run TO shiftmind_runtime"
    ) in migration
    assert "GRANT UPDATE" not in "\n".join(
        line
        for line in migration.splitlines()
        if "run_snapshot TO shiftmind_runtime" in line
        or "schedule_version TO shiftmind_runtime" in line
    )


@pytest.mark.postgres
def test_live_schedule_grants_keep_immutable_tables_insert_select_only(
    governed_postgres_engine,
) -> None:
    with governed_postgres_engine.connect() as connection:
        rows = connection.execute(
            text(
                "SELECT table_name, privilege_type FROM information_schema.role_table_grants "
                "WHERE grantee = 'shiftmind_runtime' AND table_name IN "
                "('run_snapshot','schedule_run','schedule_version','schedule_assignment')"
            )
        ).all()

    grants: dict[str, set[str]] = {}
    for table_name, privilege in rows:
        grants.setdefault(table_name, set()).add(privilege)
    assert grants["run_snapshot"] == {"SELECT", "INSERT"}
    assert grants["schedule_version"] == {"SELECT", "INSERT"}
    assert grants["schedule_assignment"] == {"SELECT", "INSERT"}
    assert grants["schedule_run"] == {"SELECT", "INSERT"}
    with governed_postgres_engine.connect() as connection:
        update_columns = set(
            connection.execute(
                text(
                    "SELECT column_name FROM information_schema.column_privileges "
                    "WHERE grantee = 'shiftmind_runtime' AND table_name = 'schedule_run' "
                    "AND privilege_type = 'UPDATE'"
                )
            ).scalars()
        )
    assert update_columns == {
        "status", "reason", "candidate_schedule_version_id", "finished_at"
    }


@pytest.mark.postgres
def test_live_candidate_check_rejects_non_completed_run(governed_postgres_engine) -> None:
    ids = {name: uuid4() for name in (
        "organization", "site", "scenario", "scenario_version", "actor",
        "conversation", "proposal", "proposal_version", "snapshot", "run", "candidate",
    )}
    with governed_postgres_engine.begin() as connection:
        connection.execute(text("SELECT set_config('app.site_id', :site, true)"), {"site": str(ids["site"])})
        connection.execute(text("INSERT INTO organization (id,name) VALUES (:id,'Org')"), {"id": ids["organization"]})
        connection.execute(text("INSERT INTO site (id,organization_id,name) VALUES (:id,:org,'Site')"), {"id": ids["site"], "org": ids["organization"]})
        connection.execute(text("INSERT INTO app_user (id,idp_subject,email) VALUES (:id,:subject,'planner@example.test')"), {"id": ids["actor"], "subject": f"subject-{ids['actor']}"})
        connection.execute(text("INSERT INTO scenario (id,site_id,fixture_id,name) VALUES (:id,:site,'fixture','Scenario')"), {"id": ids["scenario"], "site": ids["site"]})
        connection.execute(text("INSERT INTO scenario_version (id,site_id,scenario_id,fixture_id,version,payload,checksum_digest) VALUES (:id,:site,:scenario,'fixture','v1','{}'::jsonb,:digest)"), {"id": ids["scenario_version"], "site": ids["site"], "scenario": ids["scenario"], "digest": "a" * 64})
        connection.execute(text("INSERT INTO conversation (id,site_id,scenario_id,scenario_version_id,created_by_actor_id) VALUES (:id,:site,:scenario,:version,:actor)"), {"id": ids["conversation"], "site": ids["site"], "scenario": ids["scenario"], "version": ids["scenario_version"], "actor": ids["actor"]})
        connection.execute(text("INSERT INTO proposal (id,site_id,scenario_id,scenario_version_id,conversation_id,created_by_actor_id) VALUES (:id,:site,:scenario,:version,:conversation,:actor)"), {"id": ids["proposal"], "site": ids["site"], "scenario": ids["scenario"], "version": ids["scenario_version"], "conversation": ids["conversation"], "actor": ids["actor"]})
        connection.execute(text("INSERT INTO proposal_version (id,site_id,proposal_id,version_ordinal,payload,canonical_hash) VALUES (:id,:site,:proposal,1,'{}'::jsonb,:digest)"), {"id": ids["proposal_version"], "site": ids["site"], "proposal": ids["proposal"], "digest": "b" * 64})
        connection.execute(text("INSERT INTO run_snapshot (id,site_id,scenario_id,scenario_version_id,proposal_id,proposal_version_id,payload,canonical_hash,accepted_at) VALUES (:id,:site,:scenario,:version,:proposal,:proposal_version,'{}'::jsonb,:digest,CURRENT_TIMESTAMP)"), {"id": ids["snapshot"], "site": ids["site"], "scenario": ids["scenario"], "version": ids["scenario_version"], "proposal": ids["proposal"], "proposal_version": ids["proposal_version"], "digest": "c" * 64})
        connection.execute(text("INSERT INTO schedule_run (id,site_id,run_snapshot_id,status) VALUES (:id,:site,:snapshot,'solver_running')"), {"id": ids["run"], "site": ids["site"], "snapshot": ids["snapshot"]})
        connection.execute(text("INSERT INTO schedule_version (id,site_id,schedule_run_id,scenario_id,scenario_version_id,proposal_id,proposal_version_id,solver_status,payload,canonical_hash) VALUES (:id,:site,:run,:scenario,:version,:proposal,:proposal_version,'OPTIMAL','{}'::jsonb,:digest)"), {"id": ids["candidate"], "site": ids["site"], "run": ids["run"], "scenario": ids["scenario"], "version": ids["scenario_version"], "proposal": ids["proposal"], "proposal_version": ids["proposal_version"], "digest": "d" * 64})
        with pytest.raises(IntegrityError, match="ck_schedule_run_candidate_completed"):
            with connection.begin_nested():
                connection.execute(text("UPDATE schedule_run SET status='solver_failed', candidate_schedule_version_id=:candidate WHERE id=:run"), {"candidate": ids["candidate"], "run": ids["run"]})
