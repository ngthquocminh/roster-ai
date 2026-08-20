"""Schema-level contracts for the governed PostgreSQL aggregate slices."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy import BigInteger, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID

from adapters.postgres.schema import metadata


BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "organization",
    "site",
    "scenario",
    "scenario_version",
    "fixture_lineage",
    "evidence_reference",
    "app_user",
    "membership",
    "auth.session_index",
    "auth.login_handshake",
    "conversation",
    "message",
    "agent_run",
    "persisted_event",
    "proposal",
    "proposal_version",
    "command_idempotency",
    "run_snapshot",
    "schedule_run",
    "schedule_version",
    "schedule_assignment",
    "workflow.job_queue",
}
SITE_OWNED_TABLES = {
    "scenario",
    "scenario_version",
    "fixture_lineage",
    "evidence_reference",
    "membership",
    "conversation",
    "message",
    "agent_run",
    "persisted_event",
    "proposal",
    "proposal_version",
    "command_idempotency",
    "run_snapshot",
    "schedule_run",
    "schedule_version",
    "schedule_assignment",
    "workflow.job_queue",
}


def test_metadata_contains_only_story_owned_tables() -> None:
    assert set(metadata.tables) == EXPECTED_TABLES


def test_primary_keys_are_server_generated_uuids() -> None:
    for table in metadata.tables.values():
        primary_key = list(table.primary_key.columns)
        assert len(primary_key) == 1
        assert isinstance(primary_key[0].type, UUID)
        assert primary_key[0].server_default is not None


def test_site_owned_tables_carry_required_site_id() -> None:
    for table_name in SITE_OWNED_TABLES:
        site_id = metadata.tables[table_name].c.site_id
        assert isinstance(site_id.type, UUID)
        assert site_id.nullable is False


def test_scenario_version_stores_raw_payload_and_canonical_checksum() -> None:
    table = metadata.tables["scenario_version"]

    assert isinstance(table.c.payload.type, JSONB)
    assert table.c.payload.nullable is False
    assert {
        "fixture_id",
        "version",
        "checksum_algorithm",
        "checksum_schema_version",
        "checksum_digest",
        "imported_at",
    }.issubset(table.c.keys())
    unique_columns = {
        tuple(constraint.columns.keys())
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert ("site_id", "fixture_id", "version") in unique_columns


def test_fixture_lineage_points_to_a_source_and_scenario_version() -> None:
    table = metadata.tables["fixture_lineage"]

    assert {
        "scenario_version_id",
        "source_package",
        "source_path",
    }.issubset(table.c.keys())


def test_first_revision_enforces_rls_and_runtime_immutability() -> None:
    migration = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "d128d081ab48_establish_governed_fixture_history.py"
    ).read_text(encoding="utf-8")

    for table_name in {
        "site",
        "scenario",
        "scenario_version",
        "fixture_lineage",
        "evidence_reference",
    }:
        assert f'"{table_name}":' in migration
    assert "ENABLE ROW LEVEL SECURITY" in migration
    assert "FORCE ROW LEVEL SECURITY" in migration
    assert "shiftmind_runtime" in migration
    assert "GRANT SELECT, INSERT ON scenario_version TO shiftmind_runtime" in migration
    assert "GRANT UPDATE" not in migration
    assert "GRANT DELETE" not in migration
    assert "REVOKE UPDATE, DELETE ON scenario_version FROM shiftmind_runtime" in migration


def test_agent_run_status_grant_revision_is_column_scoped_and_reversible() -> None:
    migration = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "c7d6e5f4a3b2_grant_agent_run_status_update.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str = "a4f92d7c8e31"' in migration
    assert "GRANT UPDATE (status) ON agent_run TO shiftmind_runtime" in migration
    assert "REVOKE UPDATE (status) ON agent_run FROM shiftmind_runtime" in migration
    assert "ADD COLUMN" not in migration.upper()


def test_schedule_run_resource_version_revision_is_narrow_and_reversible() -> None:
    table = metadata.tables["schedule_run"]
    assert isinstance(table.c.resource_version.type, BigInteger)
    assert table.c.resource_version.nullable is False
    assert str(table.c.resource_version.server_default.arg) == "1"

    migration = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "b3c4d5e6f7a8_add_schedule_run_resource_version.py"
    ).read_text(encoding="utf-8")
    assert 'down_revision: str = "a2b3c4d5e6f7"' in migration
    assert "GRANT UPDATE (resource_version) ON schedule_run TO shiftmind_runtime" in migration
    assert (
        "GRANT UPDATE (cancellation_requested) ON workflow.job_queue "
        "TO shiftmind_runtime"
    ) in migration
    assert "REVOKE UPDATE (cancellation_requested) ON workflow.job_queue" in migration
    assert "REVOKE UPDATE (resource_version) ON schedule_run" in migration
