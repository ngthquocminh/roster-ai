"""Add the governed durable-conversation aggregate.

Revision ID: a4f92d7c8e31
Revises: 5e2a4c9d1f70
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a4f92d7c8e31"
down_revision: str = "5e2a4c9d1f70"
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
        "conversation", *_common(),
        sa.Column("scenario_id", UUID, nullable=False),
        sa.Column("scenario_version_id", UUID, nullable=False),
        sa.Column("created_by_actor_id", UUID, nullable=False),
        sa.Column("resource_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["created_by_actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_conversation_scenario_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_conversation_version_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_conversation_id_site"),
    )
    op.create_table(
        "message", *_common(),
        sa.Column("conversation_id", UUID, nullable=False), sa.Column("actor_id", UUID, nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("length(btrim(text)) > 0", name="ck_message_text_nonempty"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_message_conversation_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_message_id_site"),
    )
    op.create_table(
        "agent_run", *_common(),
        sa.Column("conversation_id", UUID, nullable=False), sa.Column("message_id", UUID, nullable=False),
        sa.Column("status", sa.String(40), server_default=sa.text("'agent_queued'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("status IN ('agent_queued','agent_running','approval_required','agent_completed','agent_timed_out','agent_cancelled','agent_failed')", name="ck_agent_run_status"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_agent_run_conversation_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["message_id", "site_id"], ["message.id", "message.site_id"], name="fk_agent_run_message_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_agent_run_id_site"),
    )
    op.create_table(
        "persisted_event", *_common(),
        sa.Column("stream_id", UUID, nullable=False), sa.Column("sequence", sa.Numeric(38, 0), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("resource_version", sa.BigInteger(), nullable=False), sa.Column("request_id", UUID, nullable=False),
        sa.Column("conversation_id", UUID, nullable=False), sa.Column("agent_run_id", UUID, nullable=False),
        sa.Column("actor_id", UUID, nullable=False), sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_persisted_event_conversation_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_run_id", "site_id"], ["agent_run.id", "agent_run.site_id"], name="fk_persisted_event_agent_run_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("stream_id", "sequence", name="uq_persisted_event_stream_sequence"),
    )
    for table in ("conversation", "message", "agent_run", "persisted_event"):
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_site_isolation ON {table} USING (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid) WITH CHECK (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid)")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO shiftmind_runtime")
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM shiftmind_runtime")
    op.execute("GRANT UPDATE (resource_version) ON conversation TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (resource_version) ON conversation FROM shiftmind_runtime")
    for table in reversed(("conversation", "message", "agent_run", "persisted_event")):
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM shiftmind_runtime")
        op.execute(f"DROP POLICY IF EXISTS {table}_site_isolation ON {table}")
    for table in ("persisted_event", "agent_run", "message", "conversation"):
        op.drop_table(table)
