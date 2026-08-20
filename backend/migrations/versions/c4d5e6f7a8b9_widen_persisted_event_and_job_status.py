"""Widen persisted events for run streams and add terminal job failure.

Revision ID: c4d5e6f7a8b9
Revises: b3c4d5e6f7a8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c4d5e6f7a8b9"
down_revision: str = "b3c4d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_STREAM_OWNER_CHECK = """
    (conversation_id IS NOT NULL AND schedule_run_id IS NULL
        AND stream_id = conversation_id)
    OR
    (schedule_run_id IS NOT NULL AND conversation_id IS NULL
        AND stream_id = schedule_run_id)
"""


def upgrade() -> None:
    op.alter_column("persisted_event", "conversation_id", nullable=True)
    op.alter_column("persisted_event", "agent_run_id", nullable=True)
    op.add_column(
        "persisted_event",
        sa.Column("schedule_run_id", sa.UUID(), nullable=True),
    )
    op.drop_constraint(
        "ck_persisted_event_stream_is_conversation",
        "persisted_event",
        type_="check",
    )
    op.create_foreign_key(
        "fk_persisted_event_schedule_run_site",
        "persisted_event",
        "schedule_run",
        ["schedule_run_id", "site_id"],
        ["id", "site_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_persisted_event_stream_owner",
        "persisted_event",
        _STREAM_OWNER_CHECK,
    )
    op.create_index(
        "ix_persisted_event_schedule_run_id",
        "persisted_event",
        ["schedule_run_id"],
    )
    op.drop_constraint(
        "ck_job_queue_status",
        "job_queue",
        schema="workflow",
        type_="check",
    )
    op.create_check_constraint(
        "ck_job_queue_status",
        "job_queue",
        "status IN ('queued','leased','completed','failed')",
        schema="workflow",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_job_queue_status",
        "job_queue",
        schema="workflow",
        type_="check",
    )
    op.create_check_constraint(
        "ck_job_queue_status",
        "job_queue",
        "status IN ('queued','leased','completed')",
        schema="workflow",
    )
    op.execute("DELETE FROM persisted_event WHERE schedule_run_id IS NOT NULL")
    op.drop_index("ix_persisted_event_schedule_run_id", table_name="persisted_event")
    op.drop_constraint(
        "ck_persisted_event_stream_owner",
        "persisted_event",
        type_="check",
    )
    op.drop_constraint(
        "fk_persisted_event_schedule_run_site",
        "persisted_event",
        type_="foreignkey",
    )
    op.drop_column("persisted_event", "schedule_run_id")
    op.create_check_constraint(
        "ck_persisted_event_stream_is_conversation",
        "persisted_event",
        "stream_id = conversation_id",
    )
    op.alter_column("persisted_event", "agent_run_id", nullable=False)
    op.alter_column("persisted_event", "conversation_id", nullable=False)
