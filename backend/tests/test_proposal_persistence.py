from __future__ import annotations

import ast
from pathlib import Path
from uuid import UUID

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID

from adapters.postgres.schema import metadata
from application.contracts.proposal import ProposalV1
from application.ports.conversation import ClaimedAgentRunV1
from application.use_cases.finalize_agent_run import finalize_agent_run
from api.main import app


BACKEND_ROOT = Path(__file__).resolve().parents[1]


def test_proposal_metadata_has_governed_aggregate_tables() -> None:
    proposal = metadata.tables["proposal"]
    version = metadata.tables["proposal_version"]
    idempotency = metadata.tables["command_idempotency"]

    assert {
        "id", "site_id", "scenario_id", "scenario_version_id",
        "conversation_id", "created_by_actor_id", "state",
        "current_version_id", "resource_version", "created_at",
    } == set(proposal.c.keys())
    assert isinstance(version.c.payload.type, JSONB)
    assert isinstance(version.c.proposal_id.type, PostgresUUID)
    assert isinstance(idempotency.c.response_payload.type, JSONB)

    version_uniques = {
        tuple(item.columns.keys())
        for item in version.constraints
        if isinstance(item, UniqueConstraint)
    }
    idempotency_uniques = {
        tuple(item.columns.keys())
        for item in idempotency.constraints
        if isinstance(item, UniqueConstraint)
    }
    assert ("proposal_id", "version_ordinal") in version_uniques
    assert ("site_id", "actor_id", "operation", "body_hash") in idempotency_uniques
    assert any("state IN ('active','rejected')" in str(item.sqltext) for item in proposal.constraints if isinstance(item, CheckConstraint))


def test_proposal_migration_enforces_rls_composite_identity_and_runtime_grants() -> None:
    migration = (
        BACKEND_ROOT
        / "migrations"
        / "versions"
        / "e9f0a1b2c3d4_add_reversible_proposals.py"
    ).read_text(encoding="utf-8")

    assert 'down_revision: str = "c7d6e5f4a3b2"' in migration
    for table in ("proposal", "proposal_version", "command_idempotency"):
        assert f'"{table}"' in migration
    assert 'for table in ("proposal", "proposal_version", "command_idempotency")' in migration
    assert "ALTER TABLE {table} ENABLE ROW LEVEL SECURITY" in migration
    assert "ALTER TABLE {table} FORCE ROW LEVEL SECURITY" in migration
    assert "CREATE POLICY {table}_site_isolation" in migration
    assert "GRANT SELECT, INSERT ON {table} TO shiftmind_runtime" in migration
    assert "GRANT UPDATE (state, current_version_id, resource_version) ON proposal TO shiftmind_runtime" in migration
    assert "REVOKE UPDATE, DELETE ON {table} FROM shiftmind_runtime" in migration


def test_draft_finalization_composes_both_repositories_on_one_connection() -> None:
    calls: list[tuple[str, object]] = []
    connection = object()
    claimed = ClaimedAgentRunV1(
        agent_run_id=UUID(int=1),
        conversation_id=UUID(int=2),
        scenario_id=UUID(int=3),
        scenario_version_id=UUID(int=4),
        site_id=UUID(int=5),
        actor_id=UUID(int=6),
        membership_id=UUID(int=7),
        prompt="Draft a repair",
    )
    proposal = ProposalV1(
        proposal_id=UUID(int=8),
        proposal_version_id=UUID(int=9),
        scenario_id=claimed.scenario_id,
        scenario_version_id=claimed.scenario_version_id,
        consequence_summary="Preserves all existing locks.",
        canonical_hash="a" * 64,
    )

    class Proposals:
        def create_draft(self, used_connection, **kwargs):
            calls.append(("proposal", used_connection))
            assert kwargs["proposal"] is proposal
            return proposal

    class Conversations:
        def finish_agent_run(self, used_connection, **kwargs):
            calls.append(("conversation", used_connection))
            assert kwargs["payload"] is proposal
            return "completed"

    result = finalize_agent_run(
        Conversations(), Proposals(), connection,
        claimed=claimed,
        status="agent_completed",
        payload=proposal,
        request_id=UUID(int=10),
    )

    assert result == "completed"
    assert calls == [("proposal", connection), ("conversation", connection)]


def test_proposal_routes_do_not_widen_the_scenario_command_surface() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/proposals/{proposal_id}"]) >= {"get"}
    assert set(paths["/api/v1/proposals/{proposal_id}/revisions"]) >= {"post"}
    assert set(paths["/api/v1/proposals/{proposal_id}/rejection"]) >= {"post"}
    assert all(
        "post" not in operations
        for path, operations in paths.items()
        if path.startswith("/api/v1/scenarios")
    )


def test_proposal_commands_cannot_mutate_the_nonexistent_baseline_pointer() -> None:
    """Until Story 4.3 adds a baseline pointer, imported schema tables prove scope.

    This deliberately stands in for a pointer assertion that cannot yet exist;
    Story 4.3 must replace it with a direct unchanged-pointer proof.
    """
    path = BACKEND_ROOT / "adapters" / "postgres" / "proposal.py"
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imported_schema_names = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "adapters.postgres.schema"
        for alias in node.names
    }
    assert imported_schema_names == {
        "proposal_table", "proposal_version", "command_idempotency"
    }
