"""Add soft-archive to conversations.

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "f7a8b9c0d1e2"
down_revision: str = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversation", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    # `a4f92d7c8e31` revoked blanket UPDATE/DELETE on this table; grant only
    # the one column the archive command needs to write, same shape as
    # `c7d6e5f4a3b2`'s single-column grant on `agent_run.status`.
    op.execute("GRANT UPDATE (archived_at) ON conversation TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (archived_at) ON conversation FROM shiftmind_runtime")
    op.drop_column("conversation", "archived_at")
