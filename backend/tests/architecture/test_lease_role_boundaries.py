"""Structural least-privilege proof for the Workflow lease boundary."""
from __future__ import annotations

from pathlib import Path

from adapters.postgres.schema import job_queue


BACKEND = Path(__file__).resolve().parents[2]
WORKER = BACKEND / "worker" / "lease_worker.py"
MIGRATION = (
    BACKEND
    / "migrations"
    / "versions"
    / "a2b3c4d5e6f7_add_job_queue_and_lease_functions.py"
)


def test_job_queue_metadata_is_workflow_owned_and_closed() -> None:
    assert job_queue.schema == "workflow"
    assert set(job_queue.c.keys()) == {
        "id",
        "site_id",
        "job_type",
        "status",
        "schedule_run_id",
        "actor_id",
        "attempt_id",
        "contract_version",
        "capability_version",
        "idempotency_key",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "fencing_epoch",
        "cancellation_requested",
        "created_at",
    }
    constraints = "\n".join(
        str(constraint.sqltext)
        for constraint in job_queue.constraints
        if hasattr(constraint, "sqltext")
    )
    assert "schedule_run_execute" in constraints
    assert all(value in constraints for value in ("queued", "leased", "completed"))
    assert {column.name for index in job_queue.indexes for column in index.columns} >= {
        "status",
        "lease_expires_at",
    }


def lease_role_holds_no_table_grant(source: str) -> bool:
    """The structural guard itself, named so it can be driven against a
    deliberately broken source as well as the real one."""
    lease_lines = "\n".join(
        line for line in source.splitlines() if "shiftmind_lease" in line
    )
    return "GRANT SELECT" not in lease_lines


def test_migration_creates_a_lease_only_role_and_narrow_runtime_updates() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE SCHEMA workflow AUTHORIZATION shiftmind_owner" in source
    assert "CREATE ROLE shiftmind_lease" in source
    assert "NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS" in source
    assert "GRANT SELECT, INSERT ON workflow.job_queue TO shiftmind_runtime" in source
    assert "GRANT UPDATE (status, heartbeat_at) ON workflow.job_queue TO shiftmind_runtime" in source
    assert lease_role_holds_no_table_grant(source)
    assert "ENABLE ROW LEVEL SECURITY" in source
    assert "FORCE ROW LEVEL SECURITY" in source


def test_owner_held_lease_functions_are_fixed_and_non_public() -> None:
    source = MIGRATION.read_text(encoding="utf-8")
    assert "CREATE FUNCTION workflow.lease_next_job" in source
    assert "FOR UPDATE SKIP LOCKED" in source
    assert "fencing_epoch = job.fencing_epoch + 1" in source
    assert "attempt_id = gen_random_uuid()" in source
    assert "CREATE FUNCTION workflow.renew_job_lease" in source
    assert "fencing_epoch = p_fencing_epoch" in source
    assert source.count("SECURITY DEFINER") == 2
    assert source.count("SET search_path = pg_catalog, workflow") == 2
    assert "REVOKE EXECUTE ON FUNCTION workflow.lease_next_job(text, integer) FROM PUBLIC" in source
    assert "GRANT EXECUTE ON FUNCTION workflow.lease_next_job(text, integer) TO shiftmind_lease" in source
    assert "REVOKE EXECUTE ON FUNCTION workflow.renew_job_lease(uuid, bigint, integer) FROM PUBLIC" in source
    assert "GRANT EXECUTE ON FUNCTION workflow.renew_job_lease(uuid, bigint, integer) TO shiftmind_runtime" in source
    assert "EXECUTE format(" not in source


def test_structural_guard_would_observe_a_broad_lease_role_grant() -> None:
    """Retro action A2: observe the guard FAILING with its subject broken.

    The previous version of this test asserted that a locally-constructed
    string contained itself — it never read the migration and could not fail.
    This one drives the real predicate against the real source with one broad
    grant injected, so the guard is proven to discriminate.
    """
    source = MIGRATION.read_text(encoding="utf-8")
    assert lease_role_holds_no_table_grant(source)

    widened = source + '\nop.execute("GRANT SELECT ON workflow.job_queue TO shiftmind_lease")\n'
    assert not lease_role_holds_no_table_grant(widened)


def test_worker_opens_lease_and_domain_roles_in_separate_contexts() -> None:
    source = WORKER.read_text(encoding="utf-8")
    assert 'isolation_level="AUTOCOMMIT"' in source
    assert 'SET ROLE shiftmind_lease' in source
    assert 'SET LOCAL ROLE shiftmind_runtime' in source
    assert "set_config('app.site_id'" in source
    assert source.count("lease_and_execute_schedule_run(") == 1
    assert "workflow.job_queue" not in source
