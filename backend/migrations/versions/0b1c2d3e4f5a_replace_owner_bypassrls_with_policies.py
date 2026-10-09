"""Replace shiftmind_owner's BYPASSRLS with an owner-exempt policy per RLS table.

Revision ID: 0b1c2d3e4f5a
Revises: a8b9c0d1e2f3

WHY (Story 6.2 D2). The RDS master is `NOSUPERUSER CREATEROLE`, and in
PostgreSQL 18 `CREATEROLE` cannot grant `BYPASSRLS`. A chain whose owner role
needs that attribute cannot run on RDS. The exemption the attribute gave is
replaced 1:1 by one `<table>_owner_exempt` policy, `AS PERMISSIVE FOR ALL TO
shiftmind_owner USING (true) WITH CHECK (true)`, on every table that has row
level security. Who can see what does not change: shiftmind_owner, and the
migrator that inherits it, keep exactly the exemption they had, and no runtime
credential can reach shiftmind_owner. Local, CI and RDS now share one model.

Roles are cluster-global, so this flips shiftmind_owner for every database in
the cluster. A local database still at the previous head loses its auth and
leasing paths until it is upgraded too; `bootstrap_local` does that.

The tables are enumerated from `pg_class` here, not listed by hand, so a table
that gained RLS earlier in the chain cannot be missed. A table that gains RLS
in a LATER revision must add its own policy; `check_db_privileges`
(`every_rls_table_has_an_owner_exempt_policy`) and the coverage test go red
until it does.
"""
from typing import Sequence, Union

from alembic import op
from sqlalchemy import text

revision: str = "0b1c2d3e4f5a"
down_revision: str = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWNER_EXEMPT_SUFFIX = "_owner_exempt"


def _rls_tables() -> list[tuple[str, str]]:
    rows = op.get_bind().execute(
        text(
            "SELECT n.nspname, c.relname "
            "FROM pg_class AS c "
            "JOIN pg_namespace AS n ON n.oid = c.relnamespace "
            "WHERE c.relrowsecurity AND c.relkind IN ('r', 'p') "
            "ORDER BY n.nspname, c.relname"
        )
    ).all()
    return [(row.nspname, row.relname) for row in rows]


def _quote(identifier: str) -> str:
    return op.get_bind().dialect.identifier_preparer.quote_identifier(identifier)


def upgrade() -> None:
    bind = op.get_bind()
    owner_bypasses = bind.execute(
        text("SELECT rolbypassrls FROM pg_roles WHERE rolname = 'shiftmind_owner'")
    ).scalar_one()
    if owner_bypasses:
        # Only on a cluster a superuser migrated before this revision; such a
        # migrator is a superuser and may clear the attribute.
        op.execute("ALTER ROLE shiftmind_owner NOBYPASSRLS")
    # The policies below apply to the migrator only through this membership.
    # 5e2a4c9d1f70 grants it on a fresh cluster; an older cluster lacks it.
    op.execute("GRANT shiftmind_owner TO CURRENT_USER WITH INHERIT TRUE, SET TRUE")

    for schema, table in _rls_tables():
        policy = f"{table}{OWNER_EXEMPT_SUFFIX}"
        exists = bind.execute(
            text(
                "SELECT 1 FROM pg_policies "
                "WHERE schemaname = :schema AND tablename = :table "
                "AND policyname = :policy"
            ),
            {"schema": schema, "table": table, "policy": policy},
        ).first()
        if exists is not None:
            continue
        op.execute(
            f"CREATE POLICY {_quote(policy)} ON {_quote(schema)}.{_quote(table)} "
            "AS PERMISSIVE FOR ALL TO shiftmind_owner USING (true) WITH CHECK (true)"
        )


def downgrade() -> None:
    bind = op.get_bind()
    for schema, table in _rls_tables():
        op.execute(
            f"DROP POLICY IF EXISTS {_quote(table + OWNER_EXEMPT_SUFFIX)} "
            f"ON {_quote(schema)}.{_quote(table)}"
        )
    is_superuser = bind.execute(
        text("SELECT rolsuper FROM pg_roles WHERE rolname = current_user")
    ).scalar_one()
    if is_superuser:
        op.execute("ALTER ROLE shiftmind_owner BYPASSRLS")
