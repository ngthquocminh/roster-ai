"""Establish governed, site-scoped fixture history.

Revision ID: d128d081ab48
Revises:
Create Date: 2026-07-24 14:25:18.479149

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "d128d081ab48"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create only the aggregates owned by Story 1.1."""
    op.create_table(
        "organization",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "site",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column(
            "organization_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["organization_id"],
            ["organization.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "scenario",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fixture_id", sa.String(length=200), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "site_id",
            "fixture_id",
            name="uq_scenario_site_fixture",
        ),
        sa.UniqueConstraint("id", "site_id", name="uq_scenario_id_site"),
    )
    op.create_table(
        "scenario_version",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("scenario_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("fixture_id", sa.String(length=200), nullable=False),
        sa.Column("version", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column(
            "checksum_algorithm",
            sa.String(length=20),
            server_default=sa.text("'sha256'"),
            nullable=False,
        ),
        sa.Column(
            "checksum_schema_version",
            sa.String(length=40),
            server_default=sa.text("'rfc8785-v1'"),
            nullable=False,
        ),
        sa.Column("checksum_digest", sa.String(length=64), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "checksum_algorithm = 'sha256'",
            name="ck_scenario_version_checksum_algorithm",
        ),
        sa.CheckConstraint(
            "checksum_schema_version = 'rfc8785-v1'",
            name="ck_scenario_version_checksum_schema_version",
        ),
        sa.CheckConstraint(
            "checksum_digest ~ '^[0-9a-f]{64}$'",
            name="ck_scenario_version_checksum_digest",
        ),
        sa.ForeignKeyConstraint(
            ["scenario_id", "site_id"],
            ["scenario.id", "scenario.site_id"],
            name="fk_scenario_version_scenario_site",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "site_id",
            "fixture_id",
            "version",
            name="uq_scenario_version_site_fixture_version",
        ),
        sa.UniqueConstraint(
            "id",
            "site_id",
            name="uq_scenario_version_id_site",
        ),
    )
    op.create_table(
        "fixture_lineage",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scenario_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("source_package", sa.String(length=200), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=False),
        sa.Column(
            "imported_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id", "site_id"],
            ["scenario_version.id", "scenario_version.site_id"],
            name="fk_fixture_lineage_version_site",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "site_id",
            "scenario_version_id",
            name="uq_fixture_lineage_version_site",
        ),
    )
    op.create_table(
        "evidence_reference",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.text("gen_random_uuid()"),
            nullable=False,
        ),
        sa.Column("site_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "scenario_version_id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
        ),
        sa.Column("reference_type", sa.String(length=80), nullable=False),
        sa.Column("reference_value", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["scenario_version_id", "site_id"],
            ["scenario_version.id", "scenario_version.site_id"],
            name="fk_evidence_reference_version_site",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_runtime'
          ) THEN
            CREATE ROLE shiftmind_runtime
              NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
          END IF;
        END
        $$;
        """
    )

    rls_expressions = {
        "site": "id",
        "scenario": "site_id",
        "scenario_version": "site_id",
        "fixture_lineage": "site_id",
        "evidence_reference": "site_id",
    }
    for table_name, site_column in rls_expressions.items():
        op.execute(f'ALTER TABLE "{table_name}" ENABLE ROW LEVEL SECURITY')
        op.execute(f'ALTER TABLE "{table_name}" FORCE ROW LEVEL SECURITY')
        op.execute(
            f"""
            CREATE POLICY {table_name}_site_isolation ON "{table_name}"
            USING (
              {site_column}
              = NULLIF(current_setting('app.site_id', true), '')::uuid
            )
            WITH CHECK (
              {site_column}
              = NULLIF(current_setting('app.site_id', true), '')::uuid
            )
            """
        )

    op.execute("GRANT USAGE ON SCHEMA public TO shiftmind_runtime")
    op.execute(
        "GRANT SELECT ON organization, site, scenario, scenario_version, "
        "fixture_lineage, evidence_reference TO shiftmind_runtime"
    )
    op.execute(
        "GRANT SELECT, INSERT ON scenario_version TO shiftmind_runtime"
    )
    op.execute(
        "REVOKE UPDATE, DELETE ON scenario_version FROM shiftmind_runtime"
    )
    op.execute("REVOKE ALL ON ALL TABLES IN SCHEMA public FROM PUBLIC")

    op.execute(
        """
        CREATE FUNCTION reject_scenario_version_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
          RAISE EXCEPTION 'scenario_version rows are immutable'
            USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER scenario_version_immutable
        BEFORE UPDATE OR DELETE ON scenario_version
        FOR EACH ROW EXECUTE FUNCTION reject_scenario_version_mutation()
        """
    )


def downgrade() -> None:
    """Remove Story 1.1's bounded schema slice."""
    op.execute(
        "REVOKE ALL ON organization, site, scenario, scenario_version, "
        "fixture_lineage, evidence_reference FROM shiftmind_runtime"
    )
    op.execute("REVOKE USAGE ON SCHEMA public FROM shiftmind_runtime")
    op.execute(
        "DROP TRIGGER IF EXISTS scenario_version_immutable ON scenario_version"
    )
    op.execute("DROP FUNCTION IF EXISTS reject_scenario_version_mutation()")
    op.drop_table("evidence_reference")
    op.drop_table("fixture_lineage")
    op.drop_table("scenario_version")
    op.drop_table("scenario")
    op.drop_table("site")
    op.drop_table("organization")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_runtime'
          ) THEN
            BEGIN
              DROP ROLE shiftmind_runtime;
            EXCEPTION
              WHEN dependent_objects_still_exist THEN
                NULL;
            END;
          END IF;
        END
        $$;
        """
    )
