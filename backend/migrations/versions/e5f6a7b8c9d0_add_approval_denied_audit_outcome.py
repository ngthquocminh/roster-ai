"""Add the authoritative approval-denied audit outcome.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
"""
from typing import Sequence, Union

from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: str = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_FIVE = "('approval_requested','approval_consumed','approval_rejected','approval_expired','approval_stale')"
_SIX = "('approval_requested','approval_consumed','approval_rejected','approval_expired','approval_stale','approval_denied')"


def _replace(values: str) -> None:
    op.drop_constraint("ck_audit_event_outcome", "audit_event", type_="check")
    op.create_check_constraint(
        "ck_audit_event_outcome", "audit_event", f"outcome IN {values}"
    )


def upgrade() -> None:
    _replace(_SIX)


def downgrade() -> None:
    _replace(_FIVE)
