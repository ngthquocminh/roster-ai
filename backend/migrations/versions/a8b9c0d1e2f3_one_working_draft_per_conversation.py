"""One working draft per conversation: three-state proposals, who ended one.

Revision ID: a8b9c0d1e2f3
Revises: f7a8b9c0d1e2

Adds the `applied` proposal state, `ended_by`, `applied_version_id`, the
lifecycle CHECK, and the partial unique index that makes "at most one `active`
proposal per conversation" a database fact (AD-9 as amended, Story 5.11).

RLS BEHAVIOUR OF THE TWO DATA STEPS. `proposal` is FORCE ROW LEVEL SECURITY, so
the `ended_by` backfill and the duplicate collapse below only see rows when this
migration runs as a superuser / BYPASSRLS role. The local provisioning role
`rosterai` is the container superuser, so they do. Under a role without
BYPASSRLS both steps match zero rows, and the migration then FAILS LOUDLY rather
than half-applying: the unique-index build (index builds are not subject to RLS)
sees every duplicate and raises, and the downgrade's two-value CHECK validates
against every `applied` row and raises. Do not "fix" a zero-row data step by
setting `app.site_id` here; the fail-loud behaviour is the design.

NOT COVERED: no `applied` backfill for promotions that happened before this
revision; `current_version_id` is not re-pointed; a downgrade leaves a
conversation that held an `applied` and an `active` draft with two `active`
rows, which the old schema permits. The downgrade never deletes a row, so it is
not refused the way `c4d5e6f7a8b9` is.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a8b9c0d1e2f3"
down_revision: str = "f7a8b9c0d1e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_TWO = "state IN ('active','rejected')"
_THREE = "state IN ('active','rejected','applied')"
_LIFECYCLE = (
    "(state = 'active' AND ended_by IS NULL AND applied_version_id IS NULL) OR "
    "(state = 'rejected' AND ended_by IS NOT NULL AND applied_version_id IS NULL) OR "
    "(state = 'applied' AND ended_by = 'system' AND applied_version_id IS NOT NULL)"
)


def _replace_state_check(expression: str) -> None:
    op.drop_constraint("ck_proposal_state", "proposal", type_="check")
    op.create_check_constraint("ck_proposal_state", "proposal", expression)


def upgrade() -> None:
    _replace_state_check(_THREE)
    op.add_column("proposal", sa.Column("ended_by", sa.String(20), nullable=True))
    op.create_check_constraint(
        "ck_proposal_ended_by",
        "proposal",
        "ended_by IS NULL OR ended_by IN ('planner','assistant','system')",
    )
    op.add_column(
        "proposal",
        sa.Column("applied_version_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_proposal_applied_version_site",
        "proposal",
        "proposal_version",
        ["applied_version_id", "site_id"],
        ["id", "site_id"],
        ondelete="RESTRICT",
    )
    # Before this revision the only path to `rejected` was the planner's route.
    op.execute("UPDATE proposal SET ended_by = 'planner' WHERE state = 'rejected'")
    # Keep the newest active draft per conversation; the rest are collapsed.
    op.execute(
        """
        UPDATE proposal
           SET state = 'rejected', ended_by = 'system',
               resource_version = proposal.resource_version + 1
          FROM (
                SELECT id,
                       ROW_NUMBER() OVER (
                           PARTITION BY conversation_id
                           ORDER BY created_at DESC, id DESC
                       ) AS position
                  FROM proposal
                 WHERE state = 'active'
               ) AS ranked
         WHERE proposal.id = ranked.id AND ranked.position > 1
        """
    )
    op.create_check_constraint("ck_proposal_lifecycle", "proposal", _LIFECYCLE)
    op.create_index(
        "uq_proposal_one_active_per_conversation",
        "proposal",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("state = 'active'"),
    )
    op.execute("GRANT UPDATE (ended_by, applied_version_id) ON proposal TO shiftmind_runtime")


def downgrade() -> None:
    op.execute("REVOKE UPDATE (ended_by, applied_version_id) ON proposal FROM shiftmind_runtime")
    op.drop_index("uq_proposal_one_active_per_conversation", table_name="proposal")
    op.drop_constraint("ck_proposal_lifecycle", "proposal", type_="check")
    # Their pre-feature state (spec 2.5); the old schema has no `applied`.
    op.execute("UPDATE proposal SET state = 'active' WHERE state = 'applied'")
    op.drop_constraint("fk_proposal_applied_version_site", "proposal", type_="foreignkey")
    op.drop_column("proposal", "applied_version_id")
    op.drop_constraint("ck_proposal_ended_by", "proposal", type_="check")
    op.drop_column("proposal", "ended_by")
    _replace_state_check(_TWO)
