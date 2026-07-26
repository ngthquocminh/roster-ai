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
    op.execute(
        "REVOKE ALL ON FUNCTION auth.resolve_session(text) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION auth.resolve_session(text) TO shiftmind_runtime"
    )


def downgrade() -> None:
    """Remove Story 1.2's bounded identity schema slice."""
    op.execute(
        "REVOKE EXECUTE ON FUNCTION auth.resolve_session(text) "
        "FROM shiftmind_runtime"
    )
    op.execute("DROP FUNCTION IF EXISTS auth.resolve_session(text)")
    op.execute("REVOKE USAGE ON SCHEMA auth FROM shiftmind_runtime")
    op.execute("REVOKE ALL ON membership FROM shiftmind_runtime")
    op.execute(
        "DROP POLICY IF EXISTS membership_site_isolation ON membership"
    )
    op.execute("ALTER TABLE membership DISABLE ROW LEVEL SECURITY")
    op.drop_table("login_handshake", schema="auth")
    op.drop_table("session_index", schema="auth")
    op.execute("DROP SCHEMA auth")
    op.execute("DROP INDEX IF EXISTS uq_membership_single_active")
    op.drop_table("membership")
    op.execute("DROP INDEX IF EXISTS uq_app_user_singleton")
    op.drop_table("app_user")
