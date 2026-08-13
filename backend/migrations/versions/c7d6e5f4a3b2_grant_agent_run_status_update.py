"""Grant the runtime role the single agent-run transition column.

Revision ID: c7d6e5f4a3b2
Revises: a4f92d7c8e31
"""
from typing import Sequence, Union

from alembic import op

revision: str = "c7d6e5f4a3b2"
down_revision: str = "a4f92d7c8e31"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("GRANT UPDATE (status) ON agent_run TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (status) ON agent_run FROM shiftmind_runtime")
