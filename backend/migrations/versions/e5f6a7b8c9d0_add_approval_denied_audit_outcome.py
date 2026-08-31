"""Add the authoritative approval-denied audit outcome.

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9

DOWNGRADE IS ONE-WAY IN PRACTICE. Restoring the five-member CHECK validates
against existing rows, so it fails with "check constraint is violated by some
row" once any `approval_denied` row exists — which the decision route writes on
every refused attempt. `audit_event` is append-only and `DELETE` is revoked from
`shiftmind_runtime`; deleting authoritative audit evidence to satisfy a schema
rollback is not something this migration will do silently. To downgrade past
this revision, the denial rows must first be dealt with deliberately, as an
explicit operational decision with its own record.
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
