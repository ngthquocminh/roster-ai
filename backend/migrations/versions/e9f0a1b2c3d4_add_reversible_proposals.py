"""Add governed reversible scheduling proposals.

Revision ID: e9f0a1b2c3d4
Revises: c7d6e5f4a3b2
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e9f0a1b2c3d4"
down_revision: str = "c7d6e5f4a3b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("site_id", UUID, nullable=False),
    ]


def upgrade() -> None:
    op.create_table(
        "proposal", *_common(),
        sa.Column("scenario_id", UUID, nullable=False),
        sa.Column("scenario_version_id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("created_by_actor_id", UUID, nullable=False),
        sa.Column("state", sa.String(20), server_default=sa.text("'active'"), nullable=False),
        sa.Column("current_version_id", UUID, nullable=True),
        sa.Column("resource_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("state IN ('active','rejected')", name="ck_proposal_state"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_proposal_scenario_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_proposal_scenario_version_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_proposal_conversation_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("id", "site_id", name="uq_proposal_id_site"),
    )
    op.create_table(
        "proposal_version", *_common(),
        sa.Column("proposal_id", UUID, nullable=False),
        sa.Column("version_ordinal", sa.BigInteger(), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("canonical_hash", sa.String(64), nullable=False),
        sa.Column("checksum_algorithm", sa.String(20), server_default=sa.text("'sha256'"), nullable=False),
        sa.Column("checksum_schema_version", sa.String(40), server_default=sa.text("'rfc8785-v1'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("checksum_algorithm = 'sha256'", name="ck_proposal_version_checksum_algorithm"),
        sa.CheckConstraint("checksum_schema_version = 'rfc8785-v1'", name="ck_proposal_version_checksum_schema_version"),
        sa.CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_proposal_version_canonical_hash"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["proposal_id", "site_id"], ["proposal.id", "proposal.site_id"], name="fk_proposal_version_proposal_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", "version_ordinal", name="uq_proposal_version_ordinal"),
        sa.UniqueConstraint("id", "site_id", name="uq_proposal_version_id_site"),
    )
    op.create_foreign_key(
        "fk_proposal_current_version_site", "proposal", "proposal_version",
        ["current_version_id", "site_id"], ["id", "site_id"], ondelete="RESTRICT",
    )
    op.create_table(
        "command_idempotency", *_common(),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("operation", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(40), nullable=False),
        sa.Column("body_hash", sa.String(64), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("body_hash ~ '^[0-9a-f]{64}$'", name="ck_command_idempotency_body_hash"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        # AD-8: one effect per (actor, site, operation, key). The body hash is
        # deliberately NOT in the key — if it were, the same key with a
        # different body would be a legal second row and the constraint could
        # never fire on the case it exists to catch.
        sa.UniqueConstraint("site_id", "actor_id", "operation", "idempotency_key", name="uq_command_idempotency_request"),
        sa.UniqueConstraint("id", "site_id", name="uq_command_idempotency_id_site"),
    )
    for table in ("proposal", "proposal_version", "command_idempotency"):
        op.create_index(f"ix_{table}_site_id", table, ["site_id"])
    op.create_index("ix_proposal_conversation_id", "proposal", ["conversation_id"])
    op.create_index("ix_proposal_version_proposal_id", "proposal_version", ["proposal_id"])
    op.create_index("ix_command_idempotency_actor_operation", "command_idempotency", ["actor_id", "operation"])
    for table in ("proposal", "proposal_version", "command_idempotency"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_site_isolation ON {table} USING (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid) WITH CHECK (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid)")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO shiftmind_runtime")
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM shiftmind_runtime")
    op.execute("GRANT UPDATE (state, current_version_id, resource_version) ON proposal TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (state, current_version_id, resource_version) ON proposal FROM shiftmind_runtime")
    for table in reversed(("proposal", "proposal_version", "command_idempotency")):
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM shiftmind_runtime")
        op.execute(f"DROP POLICY IF EXISTS {table}_site_isolation ON {table}")
    op.drop_constraint("fk_proposal_current_version_site", "proposal", type_="foreignkey")
    for table in ("command_idempotency", "proposal_version", "proposal"):
        op.drop_table(table)
