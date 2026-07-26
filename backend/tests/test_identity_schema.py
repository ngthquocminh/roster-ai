"""Schema and migration contracts for Story 1.2 identity persistence."""
from __future__ import annotations

from pathlib import Path

from sqlalchemy.dialects.postgresql import UUID

from adapters.postgres.schema import metadata


BACKEND_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    BACKEND_ROOT
    / "migrations"
    / "versions"
    / "5e2a4c9d1f70_add_seeded_site_identity.py"
)


def test_identity_metadata_contains_only_the_minimal_story_tables() -> None:
    identity_tables = {
        name
        for name in metadata.tables
        if name in {"app_user", "membership"} or name.startswith("auth.")
    }

    assert identity_tables == {
        "app_user",
        "membership",
        "auth.session_index",
        "auth.login_handshake",
    }
    assert not {
        "invitation",
        "role",
        "permission",
        "role_assignment",
    }.intersection(metadata.tables)


def test_identity_metadata_has_required_columns_and_scoping() -> None:
    app_user = metadata.tables["app_user"]
    membership = metadata.tables["membership"]
    session_index = metadata.tables["auth.session_index"]
    login_handshake = metadata.tables["auth.login_handshake"]

    assert set(app_user.c) >= {
        app_user.c.id,
        app_user.c.idp_subject,
        app_user.c.email,
        app_user.c.created_at,
        app_user.c.disabled_at,
    }
    assert "site_id" not in app_user.c
    assert isinstance(membership.c.site_id.type, UUID)
    assert {
        "session_token_hash",
        "csrf_token_hash",
        "app_user_id",
        "site_id",
        "expires_at",
        "revoked_at",
    }.issubset(session_index.c.keys())
    assert {
        "state",
        "nonce",
        "code_verifier",
        "redirect_target",
        "expires_at",
        "consumed_at",
    }.issubset(login_handshake.c.keys())


def test_identity_migration_enforces_singleton_and_internal_control_boundaries() -> None:
    migration = MIGRATION_PATH.read_text(encoding="utf-8")

    assert 'down_revision: str = "d128d081ab48"' in migration
    assert "CREATE UNIQUE INDEX uq_app_user_singleton ON app_user ((true))" in migration
    assert (
        "CREATE UNIQUE INDEX uq_membership_single_active ON membership ((true)) "
        "WHERE revoked_at IS NULL"
    ) in migration
    assert "ALTER TABLE membership ENABLE ROW LEVEL SECURITY" in migration
    assert "ALTER TABLE membership FORCE ROW LEVEL SECURITY" in migration
    assert "CREATE POLICY membership_site_isolation" in migration
    assert "CREATE SCHEMA auth" in migration
    assert "REVOKE ALL ON auth.session_index FROM shiftmind_runtime" in migration
    assert "REVOKE ALL ON auth.login_handshake FROM shiftmind_runtime" in migration
    assert "CREATE FUNCTION auth.resolve_session(token_hash text)" in migration
    assert "SECURITY DEFINER" in migration
    assert "SET search_path = auth, pg_catalog" in migration
    assert "REVOKE ALL ON FUNCTION auth.resolve_session(text) FROM PUBLIC" in migration
    assert (
        "GRANT EXECUTE ON FUNCTION auth.resolve_session(text) TO shiftmind_runtime"
        in migration
    )


def test_alembic_environment_compares_named_schemas() -> None:
    env = (BACKEND_ROOT / "migrations" / "env.py").read_text(encoding="utf-8")

    assert env.count("include_schemas=True") == 3
