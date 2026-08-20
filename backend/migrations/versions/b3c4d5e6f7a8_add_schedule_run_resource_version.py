"""Add schedule-run resource version and cancellation grants.

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a8"
down_revision: str = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "schedule_run",
        sa.Column(
            "resource_version",
            sa.BigInteger(),
            server_default=sa.text("1"),
            nullable=False,
        ),
    )
    op.execute(
        "GRANT UPDATE (resource_version) ON schedule_run TO shiftmind_runtime"
    )
    op.execute("GRANT UPDATE (cancellation_requested) ON workflow.job_queue TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (cancellation_requested) ON workflow.job_queue FROM shiftmind_runtime")
    op.execute(
        "REVOKE UPDATE (resource_version) ON schedule_run FROM shiftmind_runtime"
    )
    op.drop_column("schedule_run", "resource_version")
