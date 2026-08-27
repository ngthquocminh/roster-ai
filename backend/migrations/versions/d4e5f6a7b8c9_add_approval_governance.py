"""Add approval, baseline, and append-only audit storage.

Revision ID: d4e5f6a7b8c9
Revises: c4d5e6f7a8b9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: str = "c4d5e6f7a8b9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
UUID = postgresql.UUID(as_uuid=True)


def _common() -> list[sa.Column]:
    return [
        sa.Column("id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("site_id", UUID, nullable=False),
    ]


def _secure(table: str) -> None:
    op.create_index(f"ix_{table}_site_id", table, ["site_id"])
    op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY {table}_site_isolation ON {table} USING (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid) WITH CHECK (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid)")
    op.execute(f"GRANT SELECT, INSERT ON {table} TO shiftmind_runtime")
    op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM shiftmind_runtime")


def upgrade() -> None:
    op.create_table(
        "approval_request", *_common(),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("action", sa.String(60), nullable=False),
        sa.Column("initiated_by_actor_id", UUID, nullable=False),
        sa.Column("decided_by_actor_id", UUID, nullable=True),
        sa.Column("conversation_id", UUID, nullable=False),
        sa.Column("agent_run_id", UUID, nullable=True),
        sa.Column("schedule_run_id", UUID, nullable=False),
        sa.Column("candidate_schedule_version_id", UUID, nullable=False),
        sa.Column("baseline_schedule_version", sa.String(100), nullable=True),
        sa.Column("baseline_resource_version", sa.BigInteger(), nullable=True),
        sa.Column("parameter_hash", sa.String(64), nullable=False),
        sa.Column("consequence_summary", sa.Text(), nullable=False),
        sa.Column("consequence_hash", sa.String(64), nullable=False),
        sa.Column("checksum_algorithm", sa.String(20), server_default=sa.text("'sha256'"), nullable=False),
        sa.Column("checksum_schema_version", sa.String(40), server_default=sa.text("'rfc8785-v1'"), nullable=False),
        sa.Column("policy_version", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("request_effect_key", sa.Text(), nullable=False),
        sa.Column("resource_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("pending_payload", postgresql.JSONB(), nullable=True),
        sa.CheckConstraint("state IN ('pending','consumed','rejected','expired','stale')", name="ck_approval_request_state"),
        sa.CheckConstraint("action = 'promote_baseline'", name="ck_approval_request_action"),
        sa.CheckConstraint("parameter_hash ~ '^[0-9a-f]{64}$'", name="ck_approval_request_parameter_hash"),
        sa.CheckConstraint("consequence_hash ~ '^[0-9a-f]{64}$'", name="ck_approval_request_consequence_hash"),
        sa.CheckConstraint("checksum_algorithm = 'sha256'", name="ck_approval_request_checksum_algorithm"),
        sa.CheckConstraint("checksum_schema_version = 'rfc8785-v1'", name="ck_approval_request_checksum_schema_version"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["initiated_by_actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["decided_by_actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_approval_request_conversation_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["agent_run_id", "site_id"], ["agent_run.id", "agent_run.site_id"], name="fk_approval_request_agent_run_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_run_id", "site_id"], ["schedule_run.id", "schedule_run.site_id"], name="fk_approval_request_run_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["candidate_schedule_version_id", "site_id"], ["schedule_version.id", "schedule_version.site_id"], name="fk_approval_request_candidate_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_approval_request_id_site"),
        sa.UniqueConstraint("site_id", "request_effect_key", name="uq_approval_request_effect"),
    )
    op.create_index("uq_approval_request_pending_agent_run", "approval_request", ["agent_run_id"], unique=True, postgresql_where=sa.text("state = 'pending' AND agent_run_id IS NOT NULL"))
    op.create_table(
        "site_baseline", *_common(),
        sa.Column("schedule_version_id", UUID, nullable=False),
        sa.Column("resource_version", sa.BigInteger(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("updated_by_actor_id", UUID, nullable=False),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_version_id", "site_id"], ["schedule_version.id", "schedule_version.site_id"], name="fk_site_baseline_version_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["updated_by_actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_site_baseline_id_site"), sa.UniqueConstraint("site_id", name="uq_site_baseline_site"),
    )
    op.create_table(
        "audit_event", *_common(),
        sa.Column("attempt_id", UUID, nullable=False), sa.Column("request_id", UUID, nullable=False),
        sa.Column("initiated_by_actor_id", UUID, nullable=False), sa.Column("decided_by_actor_id", UUID, nullable=True),
        sa.Column("conversation_id", UUID, nullable=True), sa.Column("agent_run_id", UUID, nullable=True),
        sa.Column("approval_id", UUID, nullable=True), sa.Column("schedule_run_id", UUID, nullable=True),
        sa.Column("action", sa.String(60), nullable=False), sa.Column("outcome", sa.String(40), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False), sa.Column("effect_key", sa.Text(), nullable=False),
        sa.Column("before_version", sa.String(100), nullable=True), sa.Column("after_version", sa.String(100), nullable=True),
        sa.Column("safe_summary", sa.Text(), nullable=False), sa.Column("parameter_hash", sa.String(64), nullable=False), sa.Column("consequence_hash", sa.String(64), nullable=False), sa.Column("policy_version", sa.String(100), nullable=False), sa.Column("app_version", sa.String(100), nullable=False), sa.Column("worker_facts", postgresql.JSONB(), nullable=False), sa.Column("evidence_refs", postgresql.JSONB(), nullable=False), sa.Column("occurred_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("outcome IN ('approval_requested','approval_consumed','approval_rejected','approval_expired','approval_stale')", name="ck_audit_event_outcome"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["initiated_by_actor_id"], ["app_user.id"], ondelete="RESTRICT"), sa.ForeignKeyConstraint(["decided_by_actor_id"], ["app_user.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_audit_event_id_site"),
    )
    op.create_index("uq_audit_event_success_effect", "audit_event", ["site_id", "effect_key", "outcome"], unique=True, postgresql_where=sa.text("success"))
    op.create_index("uq_audit_event_failure_attempt", "audit_event", ["site_id", "attempt_id"], unique=True, postgresql_where=sa.text("NOT success"))
    for table in ("approval_request", "site_baseline", "audit_event"):
        _secure(table)
    op.execute("GRANT UPDATE (state, decided_by_actor_id, decided_at, consumed_at, resource_version) ON approval_request TO shiftmind_runtime")
    op.execute("GRANT UPDATE (schedule_version_id, resource_version, updated_at, updated_by_actor_id) ON site_baseline TO shiftmind_runtime")
    op.add_column("agent_run", sa.Column("status_reason", sa.String(40), nullable=True))
    op.create_check_constraint("ck_agent_run_status_reason", "agent_run", "status_reason IS NULL OR status_reason IN ('approval_rejected','approval_expired','approval_stale')")
    op.execute("GRANT UPDATE (status, status_reason) ON agent_run TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (status, status_reason) ON agent_run FROM shiftmind_runtime")
    op.drop_constraint("ck_agent_run_status_reason", "agent_run", type_="check")
    op.drop_column("agent_run", "status_reason")
    for table in ("audit_event", "site_baseline", "approval_request"):
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM shiftmind_runtime")
        op.execute(f"DROP POLICY IF EXISTS {table}_site_isolation ON {table}")
        op.drop_table(table)
