"""Add immutable run snapshots and candidate schedule versions.

Revision ID: f1a2b3c4d5e6
Revises: e9f0a1b2c3d4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f1a2b3c4d5e6"
down_revision: str = "e9f0a1b2c3d4"
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
        "run_snapshot", *_common(),
        sa.Column("scenario_id", UUID, nullable=False),
        sa.Column("scenario_version_id", UUID, nullable=False),
        sa.Column("proposal_id", UUID, nullable=False),
        sa.Column("proposal_version_id", UUID, nullable=False),
        sa.Column("baseline_schedule_version", sa.String(100), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("canonical_hash", sa.String(64), nullable=False),
        sa.Column("checksum_algorithm", sa.String(20), server_default=sa.text("'sha256'"), nullable=False),
        sa.Column("checksum_schema_version", sa.String(40), server_default=sa.text("'rfc8785-v1'"), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("checksum_algorithm = 'sha256'", name="ck_run_snapshot_checksum_algorithm"),
        sa.CheckConstraint("checksum_schema_version = 'rfc8785-v1'", name="ck_run_snapshot_checksum_schema_version"),
        sa.CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_run_snapshot_canonical_hash"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_run_snapshot_scenario_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_run_snapshot_scenario_version_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["proposal_id", "site_id"], ["proposal.id", "proposal.site_id"], name="fk_run_snapshot_proposal_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["proposal_version_id", "site_id"], ["proposal_version.id", "proposal_version.site_id"], name="fk_run_snapshot_proposal_version_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_run_snapshot_id_site"),
    )
    op.create_table(
        "schedule_run", *_common(),
        sa.Column("run_snapshot_id", UUID, nullable=False),
        sa.Column("status", sa.String(40), server_default=sa.text("'solver_queued'"), nullable=False),
        sa.Column("reason", sa.String(100), nullable=True),
        sa.Column("candidate_schedule_version_id", UUID, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("status IN ('solver_queued','solver_running','cancellation_requested','solver_completed','solver_infeasible','solver_timed_out','solver_cancelled','solver_failed')", name="ck_schedule_run_status"),
        sa.CheckConstraint("candidate_schedule_version_id IS NULL OR status = 'solver_completed'", name="ck_schedule_run_candidate_completed"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["run_snapshot_id", "site_id"], ["run_snapshot.id", "run_snapshot.site_id"], name="fk_schedule_run_snapshot_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("id", "site_id", name="uq_schedule_run_id_site"),
    )
    op.create_table(
        "schedule_version", *_common(),
        sa.Column("schedule_run_id", UUID, nullable=False),
        sa.Column("scenario_id", UUID, nullable=False),
        sa.Column("scenario_version_id", UUID, nullable=False),
        sa.Column("proposal_id", UUID, nullable=False),
        sa.Column("proposal_version_id", UUID, nullable=False),
        sa.Column("solver_status", sa.String(20), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("canonical_hash", sa.String(64), nullable=False),
        sa.Column("checksum_algorithm", sa.String(20), server_default=sa.text("'sha256'"), nullable=False),
        sa.Column("checksum_schema_version", sa.String(40), server_default=sa.text("'rfc8785-v1'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("CURRENT_TIMESTAMP"), nullable=False),
        sa.CheckConstraint("solver_status IN ('OPTIMAL','FEASIBLE')", name="ck_schedule_version_feasible_status"),
        sa.CheckConstraint("checksum_algorithm = 'sha256'", name="ck_schedule_version_checksum_algorithm"),
        sa.CheckConstraint("checksum_schema_version = 'rfc8785-v1'", name="ck_schedule_version_checksum_schema_version"),
        sa.CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_schedule_version_canonical_hash"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_run_id", "site_id"], ["schedule_run.id", "schedule_run.site_id"], name="fk_schedule_version_run_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_schedule_version_scenario_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_schedule_version_scenario_version_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["proposal_id", "site_id"], ["proposal.id", "proposal.site_id"], name="fk_schedule_version_proposal_site", ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["proposal_version_id", "site_id"], ["proposal_version.id", "proposal_version.site_id"], name="fk_schedule_version_proposal_version_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_run_id", name="uq_schedule_version_run"),
        sa.UniqueConstraint("id", "site_id", name="uq_schedule_version_id_site"),
    )
    op.create_foreign_key(
        "fk_schedule_run_candidate_site", "schedule_run", "schedule_version",
        ["candidate_schedule_version_id", "site_id"], ["id", "site_id"], ondelete="RESTRICT",
    )
    op.create_table(
        "schedule_assignment", *_common(),
        sa.Column("schedule_version_id", UUID, nullable=False),
        sa.Column("assignment_record_id", sa.String(200), nullable=False),
        sa.Column("worker_id", sa.String(200), nullable=False),
        sa.Column("task_id", sa.String(200), nullable=False),
        sa.Column("shift_id", sa.String(200), nullable=True),
        sa.Column("start_minute", sa.BigInteger(), nullable=False),
        sa.Column("end_minute", sa.BigInteger(), nullable=False),
        sa.Column("qualification_refs", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("source", sa.String(40), nullable=False),
        sa.Column("lock_ref", sa.String(200), nullable=True),
        sa.CheckConstraint("start_minute >= 0 AND end_minute > start_minute", name="ck_schedule_assignment_interval"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["schedule_version_id", "site_id"], ["schedule_version.id", "schedule_version.site_id"], name="fk_schedule_assignment_version_site", ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_version_id", "assignment_record_id", name="uq_schedule_assignment_record"),
        sa.UniqueConstraint("id", "site_id", name="uq_schedule_assignment_id_site"),
    )
    for table in ("run_snapshot", "schedule_run", "schedule_version", "schedule_assignment"):
        op.create_index(f"ix_{table}_site_id", table, ["site_id"])
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(f"CREATE POLICY {table}_site_isolation ON {table} USING (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid) WITH CHECK (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid)")
        op.execute(f"GRANT SELECT, INSERT ON {table} TO shiftmind_runtime")
        op.execute(f"REVOKE UPDATE, DELETE ON {table} FROM shiftmind_runtime")
    op.create_index("ix_schedule_run_snapshot_id", "schedule_run", ["run_snapshot_id"])
    op.create_index("ix_schedule_version_run_id", "schedule_version", ["schedule_run_id"])
    op.create_index("ix_schedule_assignment_version_id", "schedule_assignment", ["schedule_version_id"])
    op.execute("GRANT UPDATE (status, reason, candidate_schedule_version_id, finished_at) ON schedule_run TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (status, reason, candidate_schedule_version_id, finished_at) ON schedule_run FROM shiftmind_runtime")
    for table in reversed(("run_snapshot", "schedule_run", "schedule_version", "schedule_assignment")):
        op.execute(f"REVOKE SELECT, INSERT, UPDATE, DELETE ON {table} FROM shiftmind_runtime")
        op.execute(f"DROP POLICY IF EXISTS {table}_site_isolation ON {table}")
    op.drop_constraint("fk_schedule_run_candidate_site", "schedule_run", type_="foreignkey")
    for table in ("schedule_assignment", "schedule_version", "schedule_run", "run_snapshot"):
        op.drop_table(table)
