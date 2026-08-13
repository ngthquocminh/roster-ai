"""Live PostgreSQL proofs that the API's own connection (`shiftmind_login`)
cannot bypass RLS, cannot touch the identity/session control tables
directly, and can only reach identity/session data through the auth.*
SECURITY DEFINER functions — the decision-needed finding from Story 1.2's
code review.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, text
from sqlalchemy.exc import DBAPIError

from adapters.postgres.fixture_history import PostgresFixtureHistoryAdapter
from adapters.postgres.identity import PostgresIdentitySessionStore
from adapters.postgres.schema import app_user, membership
from application.ports.session import LoginHandshake
from settings import default_settings


@pytest.fixture(scope="module")
def postgres_engine(governed_postgres_engine):
    return governed_postgres_engine


@pytest.fixture()
def restricted_engine(postgres_engine):
    """A connection authenticated as shiftmind_login — the same restricted
    role the API itself connects as — against the same throwaway database."""
    restricted_url = postgres_engine.url.set(
        username="shiftmind_login", password="shiftmind_login"
    )
    engine = create_engine(restricted_url)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.mark.postgres
def test_shiftmind_login_is_not_superuser_and_cannot_bypass_rls(
    restricted_engine,
) -> None:
    with restricted_engine.connect() as connection:
        row = connection.execute(
            text(
                "SELECT rolsuper, rolbypassrls FROM pg_roles "
                "WHERE rolname = current_user"
            )
        ).one()
    assert row.rolsuper is False
    assert row.rolbypassrls is False


@pytest.mark.postgres
def test_shiftmind_login_cannot_read_or_write_auth_tables_directly(
    restricted_engine,
) -> None:
    with pytest.raises(DBAPIError):
        with restricted_engine.connect() as connection:
            connection.execute(text("SELECT * FROM auth.session_index"))
    with pytest.raises(DBAPIError):
        with restricted_engine.connect() as connection:
            connection.execute(text("SELECT * FROM auth.login_handshake"))
    with pytest.raises(DBAPIError):
        with restricted_engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO auth.login_handshake "
                    "(state, nonce, code_verifier, redirect_target, expires_at) "
                    "VALUES ('x', 'y', 'z', 'https://example.test', now())"
                )
            )


@pytest.mark.postgres
def test_shiftmind_login_cannot_assume_the_provisioning_role(
    restricted_engine,
) -> None:
    with pytest.raises(DBAPIError):
        with restricted_engine.connect() as connection:
            connection.exec_driver_sql("SET ROLE rosterai")


@pytest.mark.postgres
def test_shiftmind_login_and_shiftmind_runtime_cannot_assume_shiftmind_owner(
    restricted_engine,
) -> None:
    """shiftmind_owner's safety comes from being unreachable, not from
    being weak (it deliberately carries BYPASSRLS) — no runtime credential
    may ever SET ROLE into it, only the migrator (already a superuser)."""
    with pytest.raises(DBAPIError):
        with restricted_engine.connect() as connection:
            connection.exec_driver_sql("SET ROLE shiftmind_owner")

    with restricted_engine.connect() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        with pytest.raises(DBAPIError):
            connection.exec_driver_sql("SET ROLE shiftmind_owner")


@pytest.mark.postgres
def test_shiftmind_owner_is_nologin_and_owns_the_auth_functions_and_tables(
    postgres_engine,
) -> None:
    with pytest.raises(DBAPIError):
        create_engine(
            postgres_engine.url.set(
                username="shiftmind_owner", password=""
            )
        ).connect()

    with postgres_engine.connect() as connection:
        owner = connection.execute(
            text("SELECT rolname FROM pg_roles WHERE rolname = 'shiftmind_owner'")
        ).scalar_one()
        assert owner == "shiftmind_owner"

        table_owners = connection.execute(
            text(
                "SELECT tablename, tableowner FROM pg_tables "
                "WHERE schemaname = 'auth'"
            )
        ).all()
        assert {row.tablename: row.tableowner for row in table_owners} == {
            "session_index": "shiftmind_owner",
            "login_handshake": "shiftmind_owner",
        }

        function_owners = connection.execute(
            text(
                "SELECT p.proname, pg_get_userbyid(p.proowner) AS owner "
                "FROM pg_proc AS p "
                "JOIN pg_namespace AS n ON n.oid = p.pronamespace "
                "WHERE n.nspname = 'auth'"
            )
        ).all()
        assert {row.proname: row.owner for row in function_owners} == {
            "resolve_session": "shiftmind_owner",
            "create_login_handshake": "shiftmind_owner",
            "consume_login_handshake": "shiftmind_owner",
            "establish_session_for_subject": "shiftmind_owner",
            "revoke_session": "shiftmind_owner",
        }


@pytest.mark.postgres
def test_shiftmind_login_can_set_role_shiftmind_runtime_but_gets_no_table_access(
    restricted_engine,
) -> None:
    with restricted_engine.connect() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        assert (
            connection.execute(text("SELECT current_user")).scalar_one()
            == "shiftmind_runtime"
        )
        with pytest.raises(DBAPIError):
            connection.execute(text("SELECT * FROM auth.session_index"))


@pytest.mark.postgres
def test_runtime_can_update_only_agent_run_status_and_cannot_delete(
    restricted_engine,
) -> None:
    with restricted_engine.connect() as connection:
        connection.exec_driver_sql("SET LOCAL ROLE shiftmind_runtime")
        privileges = {
            column: connection.execute(
                text(
                    "SELECT has_column_privilege(current_user, 'agent_run', :column, 'UPDATE')"
                ),
                {"column": column},
            ).scalar_one()
            for column in ("id", "site_id", "conversation_id", "message_id", "status", "created_at")
        }
        can_delete = connection.execute(
            text("SELECT has_table_privilege(current_user, 'agent_run', 'DELETE')")
        ).scalar_one()
    assert privileges == {
        "id": False, "site_id": False, "conversation_id": False,
        "message_id": False, "status": True, "created_at": False,
    }
    assert can_delete is False


@pytest.mark.postgres
def test_identity_store_completes_full_lifecycle_under_the_restricted_role(
    postgres_engine,
    restricted_engine,
) -> None:
    """The store the API actually uses, running under the exact connection
    the API itself uses (shiftmind_login) — not a privileged fallback."""
    suffix = uuid4().hex
    site_id = PostgresFixtureHistoryAdapter(
        default_settings().provisioning_database_url,
        engine=postgres_engine,
    ).ensure_seed_site(
        f"Role Boundary Organization {suffix}",
        f"Role Boundary Site {suffix}",
    )
    subject = f"role-boundary-planner-{suffix}"
    with postgres_engine.begin() as connection:
        app_user_id = connection.execute(
            app_user.insert()
            .values(idp_subject=subject, email=f"{subject}@example.test")
            .returning(app_user.c.id)
        ).scalar_one()
        membership_id = connection.execute(
            membership.insert()
            .values(app_user_id=app_user_id, site_id=site_id)
            .returning(membership.c.id)
        ).scalar_one()

    store = PostgresIdentitySessionStore(
        default_settings().database_url, engine=restricted_engine
    )

    # Unknown identity: no handshake exists yet.
    assert store.consume_login_handshake("does-not-exist") is None

    handshake = LoginHandshake(
        state=f"state-{suffix}",
        nonce=f"nonce-{suffix}",
        code_verifier=f"verifier-{suffix}",
        redirect_target="https://app.example.test",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    store.create_login_handshake(handshake)

    consumed = store.consume_login_handshake(handshake.state)
    assert consumed is not None
    assert consumed.nonce == handshake.nonce
    assert consumed.code_verifier == handshake.code_verifier

    # Single-use: replaying the same state fails.
    assert store.consume_login_handshake(handshake.state) is None

    # Unknown subject never establishes a session.
    assert (
        store.establish_session_for_subject(
            subject="not-provisioned",
            session_token_hash="a" * 64,
            csrf_token_hash="b" * 64,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        is None
    )

    session_token_hash = "c" * 64
    csrf_token_hash = "d" * 64
    expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
    established = store.establish_session_for_subject(
        subject=subject,
        session_token_hash=session_token_hash,
        csrf_token_hash=csrf_token_hash,
        expires_at=expires_at,
    )
    assert established is not None
    assert established.app_user_id == app_user_id
    assert established.site_id == site_id

    resolved = store.resolve_session(session_token_hash)
    assert resolved is not None
    assert resolved.app_user_id == app_user_id
    assert resolved.site_id == site_id

    assert store.revoke_session(session_token_hash) is True
    assert store.resolve_session(session_token_hash) is None
    assert store.revoke_session(session_token_hash) is False

    # A revoked membership can never establish a new session either.
    with postgres_engine.begin() as connection:
        connection.execute(
            membership.update()
            .where(membership.c.id == membership_id)
            .values(revoked_at=func.now())
        )
    assert (
        store.establish_session_for_subject(
            subject=subject,
            session_token_hash="e" * 64,
            csrf_token_hash="f" * 64,
            expires_at=expires_at,
        )
        is None
    )
