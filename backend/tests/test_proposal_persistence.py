from __future__ import annotations

import ast
from pathlib import Path
from uuid import UUID

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID as PostgresUUID

from adapters.postgres.schema import metadata
from application.contracts.activity import DraftReferenceV1
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
    # AD-8: one effect per (actor, site, operation, key). The body hash stays
    # OUT of the key so a reused key with a different body collides here rather
    # than inserting a second, indistinguishable row.
    assert ("site_id", "actor_id", "operation", "idempotency_key") in idempotency_uniques
    assert ("site_id", "actor_id", "operation", "body_hash") not in idempotency_uniques
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
            # AD-22: the repository receives the Conversation-owned reference,
            # never the Scheduling aggregate's ProposalV1. The adapter must not
            # have to read another owner's contract to build its activity.
            handed = kwargs["payload"]
            assert isinstance(handed, DraftReferenceV1)
            assert handed.proposal_id == proposal.proposal_id
            assert handed.proposal_version_id == proposal.proposal_version_id
            assert handed.consequence_summary == proposal.consequence_summary
            return "completed"

    result = finalize_agent_run(
        Conversations(), Proposals(), connection,
        claimed=claimed,
        status="agent_completed",
        payload=proposal,
        request_id=UUID(int=10),
    )

    assert result == "completed"
    # The conversation write comes FIRST: it holds the still-claimable guard, so
    # a duplicate finalisation raises AgentRunNotQueuedError instead of failing
    # on a proposal-side constraint and masking the real cause.
    assert calls == [("conversation", connection), ("proposal", connection)]


def test_proposal_routes_do_not_widen_the_scenario_command_surface() -> None:
    paths = app.openapi()["paths"]
    assert set(paths["/api/v1/proposals/{proposal_id}"]) >= {"get"}
    assert set(paths["/api/v1/proposals/{proposal_id}/revisions"]) >= {"post"}
    assert set(paths["/api/v1/proposals/{proposal_id}/rejection"]) >= {"post"}
    # Mirrors test_gate_a_mutation_audit.py's invariant, which is that scenario
    # paths expose ONLY reads. Asserting merely that "post" is absent would let a
    # future patch/put/delete through in silence.
    method_keys = {"get", "put", "post", "delete", "patch", "head", "options", "trace"}
    scenario_methods = {
        method
        for path, operations in paths.items()
        if path.startswith("/api/v1/scenarios")
        for method in operations
        if method in method_keys
    }
    assert scenario_methods <= {"get"}, scenario_methods


#: Every file that can emit SQL on a proposal command path. An import-block
#: assertion over one of them would pass against a raw
#: `connection.execute(text("UPDATE scenario ..."))`, so the scan below reads
#: the statements themselves and covers the whole path.
PROPOSAL_COMMAND_SOURCES = (
    Path("adapters") / "postgres" / "proposal.py",
    Path("application") / "use_cases" / "manage_proposal.py",
    Path("application") / "use_cases" / "finalize_agent_run.py",
    Path("api") / "routers" / "proposals.py",
)

#: Tables a proposal command may write. `scenario` and `scenario_version` are
#: absent by design: a draft never changes the baseline (AC3).
WRITABLE_TABLES = {"proposal", "proposal_version", "command_idempotency"}

FORBIDDEN_TABLES = {"scenario", "scenario_version", "fixture_lineage", "evidence_reference"}


def _sql_literals(tree: ast.AST) -> list[str]:
    return [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]


def test_proposal_commands_cannot_mutate_the_nonexistent_baseline_pointer() -> None:
    """No proposal command's SQL touches a scenario table.

    Until Story 4.3 adds a real baseline pointer this stands in for a direct
    unchanged-pointer proof, but it stands in by reading the SQL rather than the
    import block: it sees raw `text()` statements, and it covers the use case,
    the orchestrator and the router as well as the adapter.
    """
    offenders: dict[str, list[str]] = {}
    for relative in PROPOSAL_COMMAND_SOURCES:
        path = BACKEND_ROOT / relative
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        found = []
        for literal in _sql_literals(tree):
            lowered = " ".join(literal.lower().split())
            if not any(
                verb in lowered for verb in ("insert into", "update ", "delete from")
            ):
                continue
            if any(table in lowered for table in FORBIDDEN_TABLES):
                found.append(literal)
        # SQLAlchemy Core call sites: insert()/update()/delete() must name only
        # the three tables this aggregate owns.
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id not in {"insert", "update", "delete", "postgres_insert"}:
                continue
            for argument in node.args:
                name = (
                    argument.id if isinstance(argument, ast.Name)
                    else getattr(argument, "attr", None)
                )
                if name is None:
                    continue
                normalized = name.removesuffix("_table")
                if normalized not in WRITABLE_TABLES:
                    found.append(f"{node.func.id}({name})")
        if found:
            offenders[relative.as_posix()] = found
    assert not offenders, offenders


def test_the_baseline_scan_would_catch_a_raw_scenario_mutation() -> None:
    """Self-redness: the guard above must be able to go red.

    A scan that cannot fail is the failure mode this story spends a page
    warning about, so prove the detector on a synthetic offender.
    """
    tree = ast.parse(
        'connection.execute(text("UPDATE scenario_version SET is_current = false"))'
    )
    literals = _sql_literals(tree)
    assert any(
        "update " in literal.lower()
        and any(table in literal.lower() for table in FORBIDDEN_TABLES)
        for literal in literals
    )
