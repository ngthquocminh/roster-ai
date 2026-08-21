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
    """Refuse: this upgrade is not reversible without destroying governed data.

    A mechanical reversal was written first and was wrong three ways, each of
    which only fires on a database that has actually been used:

    1. Recreating the narrow ``ck_job_queue_status`` validates the predicate
       against existing rows, so the first job ``fail_job`` ever wrote as
       ``failed`` aborts the migration with a CheckViolation. ``failed`` is an
       absorbing state -- ``lease_next_job`` never re-selects it and nothing
       clears it -- so one failure blocks the downgrade permanently, and the
       three ways out (complete / requeue / delete) are each a different lie
       about what happened to that job.
    2. ``DELETE FROM persisted_event WHERE schedule_run_id IS NOT NULL``
       destroys governed run history. AD-17: "no in-product delete:
       authoritative data/evidence persist until explicit teardown."
    3. ``persisted_event`` carries FORCE ROW LEVEL SECURITY keyed on
       ``app.site_id``, which is unset during migration. On any deployment
       whose migration role lacks BYPASSRLS the DELETE matches zero rows and
       the ``conversation_id`` NOT NULL restore fails instead.

    The round-trip test covers a fresh, empty database, where none of the three
    can fire -- so a mechanical reversal would ship green and fail in the one
    situation anyone would run it. Teardown and re-provision is the supported
    path back.
    """
    raise NotImplementedError(
        "Downgrading c4d5e6f7a8b9 would delete persisted run-progress events "
        "and cannot recreate the narrow job status constraint once any job has "
        "failed. Tear down and re-provision instead."
    )
