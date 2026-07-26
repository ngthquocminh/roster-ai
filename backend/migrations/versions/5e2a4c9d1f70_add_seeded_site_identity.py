"""Add the minimal seeded-site identity and application-session structures.

Revision ID: 5e2a4c9d1f70
Revises: d128d081ab48
Create Date: 2026-07-26

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "5e2a4c9d1f70"
down_revision: str = "d128d081ab48"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create only Story 1.2's identity, membership, and session structures."""
    op.create_table(
        "app_user",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("idp_subject", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idp_subject", name="uq_app_user_idp_subject"),
    )
    op.execute(
        "CREATE UNIQUE INDEX uq_app_user_singleton ON app_user ((true))"
    )

    op.create_table(
        "membership",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["app_user.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute("CREATE UNIQUE INDEX uq_membership_single_active ON membership ((true)) WHERE revoked_at IS NULL")

    op.execute("CREATE SCHEMA auth")

    # shiftmind_owner (AD-23) owns every auth.* control table and function —
    # NOLOGIN, and no runtime credential is ever granted membership in it,
    # so the only way to act as it is the migrator (already a superuser)
    # transiently `SET ROLE`-ing in. It carries BYPASSRLS deliberately: its
    # SECURITY DEFINER functions must read the FORCE-RLS `membership` table
    # before any app.site_id exists (the same circularity resolve_session
    # solves for reads) — safety here comes from being unreachable, not
    # from being weak, unlike the NOSUPERUSER/NOBYPASSRLS runtime roles.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_owner'
          ) THEN
            CREATE ROLE shiftmind_owner
              NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE BYPASSRLS;
          END IF;
        END
        $$;
        """
    )
    op.execute("ALTER SCHEMA auth OWNER TO shiftmind_owner")
    # shiftmind_owner doesn't own app_user/membership (they're domain
    # tables, not auth-internal ones) but its SECURITY DEFINER functions
    # must read them, so it needs its own SELECT grant independent of
    # shiftmind_runtime's.
    op.execute("GRANT SELECT ON public.app_user TO shiftmind_owner")
    op.execute("GRANT SELECT ON public.membership TO shiftmind_owner")

    op.create_table(
        "session_index",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("session_token_hash", sa.String(length=64), nullable=False),
        sa.Column("csrf_token_hash", sa.String(length=64), nullable=False),
        sa.Column("app_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["app_user_id"],
            ["app_user.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "session_token_hash",
            name="uq_session_index_token_hash",
        ),
        schema="auth",
    )
    op.create_table(
        "login_handshake",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("state", sa.String(length=128), nullable=False),
        sa.Column("nonce", sa.String(length=128), nullable=False),
        sa.Column("code_verifier", sa.String(length=128), nullable=False),
        sa.Column("redirect_target", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("state", name="uq_login_handshake_state"),
        schema="auth",
    )
    op.execute("ALTER TABLE auth.session_index OWNER TO shiftmind_owner")
    op.execute("ALTER TABLE auth.login_handshake OWNER TO shiftmind_owner")

    op.execute("ALTER TABLE membership ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE membership FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        CREATE POLICY membership_site_isolation ON membership
        USING (
          site_id = NULLIF(current_setting('app.site_id', true), '')::uuid
        )
        WITH CHECK (
          site_id = NULLIF(current_setting('app.site_id', true), '')::uuid
        )
        """
    )

    op.execute("GRANT SELECT ON membership TO shiftmind_runtime")
    op.execute("GRANT USAGE ON SCHEMA auth TO shiftmind_runtime")
    op.execute("REVOKE ALL ON auth.session_index FROM shiftmind_runtime")
    op.execute("REVOKE ALL ON auth.login_handshake FROM shiftmind_runtime")
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA auth FROM PUBLIC")

    # shiftmind_login is the API's own connection role (AD-23's "API" role) —
    # a real LOGIN, but NOSUPERUSER/NOBYPASSRLS/NOINHERIT and owning no
    # grants of its own. It authenticates solely to reach `SET LOCAL ROLE
    # shiftmind_runtime` (domain reads, see get_site_context) and the
    # auth.* SECURITY DEFINER functions below. The deployment/provisioning
    # credential (Alembic, seed_planner.py) stays a separate, privileged
    # connection and is never used by the request-serving API.
    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_login'
          ) THEN
            CREATE ROLE shiftmind_login
              LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS
              PASSWORD 'shiftmind_login';
          END IF;
        END
        $$;
        """
    )
    op.execute("GRANT shiftmind_runtime TO shiftmind_login")

    op.execute(
        """
        CREATE FUNCTION auth.resolve_session(token_hash text)
        RETURNS TABLE (
          app_user_id uuid,
          site_id uuid,
          csrf_token_hash text,
          expires_at timestamptz
        )
        LANGUAGE sql
        STABLE
        SECURITY DEFINER
        SET search_path = auth, pg_catalog
        AS $$
          SELECT
            si.app_user_id,
            si.site_id,
            si.csrf_token_hash::text,
            si.expires_at
          FROM auth.session_index AS si
          JOIN public.app_user AS au
            ON au.id = si.app_user_id
           AND au.disabled_at IS NULL
          JOIN public.membership AS m
            ON m.app_user_id = si.app_user_id
           AND m.site_id = si.site_id
           AND m.revoked_at IS NULL
          WHERE si.session_token_hash = token_hash
            AND si.revoked_at IS NULL
            AND si.expires_at > statement_timestamp()
          LIMIT 1
        $$
        """
    )
    op.execute("ALTER FUNCTION auth.resolve_session(text) OWNER TO shiftmind_owner")
    op.execute(
        "REVOKE ALL ON FUNCTION auth.resolve_session(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION auth.resolve_session(text) TO shiftmind_runtime"
    )

    # The remaining identity-lifecycle operations that must not be direct
    # table access (shiftmind_runtime has none on auth.session_index /
    # auth.login_handshake, and membership is RLS-scoped by a site_id that
    # does not exist yet at login time — the same circularity AD-23's
    # resolve_session already solves for reads). Each function is
    # SECURITY DEFINER, owned by shiftmind_owner, with a fixed search_path,
    # no dynamic SQL, EXECUTE revoked from PUBLIC and granted only to
    # shiftmind_runtime.
    op.execute(
        """
        CREATE FUNCTION auth.create_login_handshake(
          p_state text,
          p_nonce text,
          p_code_verifier text,
          p_redirect_target text,
          p_expires_at timestamptz
        )
        RETURNS void
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = auth, pg_catalog
        AS $$
          INSERT INTO auth.login_handshake (
            state, nonce, code_verifier, redirect_target, expires_at
          )
          VALUES (p_state, p_nonce, p_code_verifier, p_redirect_target, p_expires_at)
        $$
        """
    )
    op.execute(
        "ALTER FUNCTION auth.create_login_handshake"
        "(text, text, text, text, timestamptz) OWNER TO shiftmind_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION auth.create_login_handshake"
        "(text, text, text, text, timestamptz) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION auth.create_login_handshake"
        "(text, text, text, text, timestamptz) TO shiftmind_runtime"
    )

    op.execute(
        """
        CREATE FUNCTION auth.consume_login_handshake(p_state text)
        RETURNS TABLE (
          state text,
          nonce text,
          code_verifier text,
          redirect_target text,
          expires_at timestamptz
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = auth, pg_catalog
        AS $$
          UPDATE auth.login_handshake
          SET consumed_at = statement_timestamp()
          WHERE login_handshake.state = p_state
            AND login_handshake.consumed_at IS NULL
            AND login_handshake.expires_at > statement_timestamp()
          RETURNING
            login_handshake.state,
            login_handshake.nonce,
            login_handshake.code_verifier,
            login_handshake.redirect_target,
            login_handshake.expires_at
        $$
        """
    )
    op.execute(
        "ALTER FUNCTION auth.consume_login_handshake(text) "
        "OWNER TO shiftmind_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION auth.consume_login_handshake(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION auth.consume_login_handshake(text) "
        "TO shiftmind_runtime"
    )

    op.execute(
        """
        CREATE FUNCTION auth.establish_session_for_subject(
          p_subject text,
          p_session_token_hash text,
          p_csrf_token_hash text,
          p_expires_at timestamptz
        )
        RETURNS TABLE (
          app_user_id uuid,
          site_id uuid
        )
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = auth, pg_catalog
        AS $$
          WITH identity AS (
            SELECT au.id AS app_user_id, m.site_id
            FROM public.app_user AS au
            JOIN public.membership AS m ON m.app_user_id = au.id
            WHERE au.idp_subject = p_subject
              AND au.disabled_at IS NULL
              AND m.revoked_at IS NULL
            LIMIT 1
          ),
          inserted AS (
            INSERT INTO auth.session_index (
              session_token_hash, csrf_token_hash, app_user_id, site_id, expires_at
            )
            SELECT
              p_session_token_hash,
              p_csrf_token_hash,
              identity.app_user_id,
              identity.site_id,
              p_expires_at
            FROM identity
            RETURNING auth.session_index.app_user_id, auth.session_index.site_id
          )
          SELECT app_user_id, site_id FROM inserted
        $$
        """
    )
    op.execute(
        "ALTER FUNCTION auth.establish_session_for_subject"
        "(text, text, text, timestamptz) OWNER TO shiftmind_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION auth.establish_session_for_subject"
        "(text, text, text, timestamptz) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION auth.establish_session_for_subject"
        "(text, text, text, timestamptz) TO shiftmind_runtime"
    )

    op.execute(
        """
        CREATE FUNCTION auth.revoke_session(p_session_token_hash text)
        RETURNS boolean
        LANGUAGE sql
        SECURITY DEFINER
        SET search_path = auth, pg_catalog
        AS $$
          WITH updated AS (
            UPDATE auth.session_index
            SET revoked_at = statement_timestamp()
            WHERE session_token_hash = p_session_token_hash
              AND revoked_at IS NULL
            RETURNING id
          )
          SELECT EXISTS (SELECT 1 FROM updated)
        $$
        """
    )
    op.execute(
        "ALTER FUNCTION auth.revoke_session(text) OWNER TO shiftmind_owner"
    )
    op.execute(
        "REVOKE ALL ON FUNCTION auth.revoke_session(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION auth.revoke_session(text) TO shiftmind_runtime"
    )


def downgrade() -> None:
    """Remove Story 1.2's bounded identity schema slice."""
    op.execute(
        "REVOKE EXECUTE ON FUNCTION auth.revoke_session(text) "
        "FROM shiftmind_runtime"
    )
    op.execute("DROP FUNCTION IF EXISTS auth.revoke_session(text)")
    op.execute(
        "REVOKE EXECUTE ON FUNCTION auth.establish_session_for_subject"
        "(text, text, text, timestamptz) FROM shiftmind_runtime"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS auth.establish_session_for_subject"
        "(text, text, text, timestamptz)"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION auth.consume_login_handshake(text) "
        "FROM shiftmind_runtime"
    )
    op.execute("DROP FUNCTION IF EXISTS auth.consume_login_handshake(text)")
    op.execute(
        "REVOKE EXECUTE ON FUNCTION auth.create_login_handshake"
        "(text, text, text, text, timestamptz) FROM shiftmind_runtime"
    )
    op.execute(
        "DROP FUNCTION IF EXISTS auth.create_login_handshake"
        "(text, text, text, text, timestamptz)"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION auth.resolve_session(text) "
        "FROM shiftmind_runtime"
    )
    op.execute("DROP FUNCTION IF EXISTS auth.resolve_session(text)")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_login'
          ) THEN
            REVOKE shiftmind_runtime FROM shiftmind_login;
            BEGIN
              DROP ROLE shiftmind_login;
            EXCEPTION
              WHEN dependent_objects_still_exist THEN
                NULL;
            END;
          END IF;
        END
        $$;
        """
    )
    op.execute("REVOKE USAGE ON SCHEMA auth FROM shiftmind_runtime")
    op.execute("REVOKE ALL ON membership FROM shiftmind_runtime")
    op.execute(
        "DROP POLICY IF EXISTS membership_site_isolation ON membership"
    )
    op.execute("ALTER TABLE membership DISABLE ROW LEVEL SECURITY")
    op.drop_table("login_handshake", schema="auth")
    op.drop_table("session_index", schema="auth")
    op.execute("REVOKE SELECT ON public.app_user FROM shiftmind_owner")
    op.execute("REVOKE SELECT ON public.membership FROM shiftmind_owner")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_owner'
          ) THEN
            BEGIN
              DROP ROLE shiftmind_owner;
            EXCEPTION
              WHEN dependent_objects_still_exist THEN
                NULL;
            END;
          END IF;
        END
        $$;
        """
    )
    op.execute("DROP SCHEMA auth")
    op.execute("DROP INDEX IF EXISTS uq_membership_single_active")
    op.drop_table("membership")
    op.execute("DROP INDEX IF EXISTS uq_app_user_singleton")
    op.drop_table("app_user")
