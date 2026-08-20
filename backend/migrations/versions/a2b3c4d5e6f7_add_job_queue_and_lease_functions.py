"""Add durable workflow jobs and the lease-only runtime role.

Revision ID: a2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a2b3c4d5e6f7"
down_revision: str = "f1a2b3c4d5e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.execute("CREATE SCHEMA workflow AUTHORIZATION shiftmind_owner")
    op.create_table(
        "job_queue",
        sa.Column(
            "id", UUID, server_default=sa.text("gen_random_uuid()"), nullable=False
        ),
        sa.Column("site_id", UUID, nullable=False),
        sa.Column(
            "job_type",
            sa.String(60),
            server_default=sa.text("'schedule_run_execute'"),
            nullable=False,
        ),
        sa.Column(
            "status", sa.String(20), server_default=sa.text("'queued'"), nullable=False
        ),
        sa.Column("schedule_run_id", UUID, nullable=False),
        sa.Column("actor_id", UUID, nullable=False),
        sa.Column("attempt_id", UUID, nullable=True),
        sa.Column("contract_version", sa.String(40), nullable=False),
        sa.Column("capability_version", sa.String(80), nullable=True),
        sa.Column("idempotency_key", sa.String(200), nullable=False),
        sa.Column("lease_owner", sa.String(200), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "fencing_epoch", sa.BigInteger(), server_default=sa.text("0"), nullable=False
        ),
        sa.Column(
            "cancellation_requested",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "job_type IN ('schedule_run_execute')", name="ck_job_queue_job_type"
        ),
        sa.CheckConstraint(
            "status IN ('queued','leased','completed')", name="ck_job_queue_status"
        ),
        sa.CheckConstraint("fencing_epoch >= 0", name="ck_job_queue_fencing_epoch"),
        sa.ForeignKeyConstraint(["site_id"], ["site.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["schedule_run_id", "site_id"],
            ["schedule_run.id", "schedule_run.site_id"],
            name="fk_job_queue_schedule_run_site",
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["actor_id"],
            ["app_user.id"],
            name="fk_job_queue_actor",
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("schedule_run_id", name="uq_job_queue_schedule_run"),
        sa.UniqueConstraint("id", "site_id", name="uq_job_queue_id_site"),
        schema="workflow",
    )
    op.create_index(
        "ix_job_queue_site_id", "job_queue", ["site_id"], schema="workflow"
    )
    op.create_index(
        "ix_job_queue_leaseable",
        "job_queue",
        ["status", "lease_expires_at", "created_at"],
        schema="workflow",
    )
    op.execute("ALTER TABLE workflow.job_queue OWNER TO shiftmind_owner")
    op.execute("ALTER TABLE workflow.job_queue ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE workflow.job_queue FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY job_queue_site_isolation ON workflow.job_queue "
        "USING (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid) "
        "WITH CHECK (site_id = NULLIF(current_setting('app.site_id', true), '')::uuid)"
    )

    op.execute(
        """
        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_lease'
          ) THEN
            CREATE ROLE shiftmind_lease
              NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS;
          END IF;
        END
        $$;
        """
    )
    op.execute("GRANT USAGE ON SCHEMA workflow TO shiftmind_runtime")
    op.execute("GRANT SELECT, INSERT ON workflow.job_queue TO shiftmind_runtime")
    op.execute("REVOKE UPDATE, DELETE ON workflow.job_queue FROM shiftmind_runtime")
    op.execute(
        "GRANT UPDATE (status, heartbeat_at) ON workflow.job_queue TO shiftmind_runtime"
    )
    op.execute("REVOKE ALL ON workflow.job_queue FROM PUBLIC")

    op.execute(
        """
        CREATE FUNCTION workflow.lease_next_job(
          p_lease_owner text,
          p_lease_seconds integer
        ) RETURNS workflow.job_queue
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, workflow
        AS $$
        DECLARE
          job workflow.job_queue%ROWTYPE;
        BEGIN
          IF p_lease_owner IS NULL OR btrim(p_lease_owner) = '' THEN
            RAISE EXCEPTION 'lease owner is required' USING ERRCODE = '22023';
          END IF;
          IF p_lease_seconds <= 0 THEN
            RAISE EXCEPTION 'lease duration must be positive' USING ERRCODE = '22023';
          END IF;

          SELECT q.* INTO job
          FROM workflow.job_queue AS q
          WHERE q.status = 'queued'
             OR (q.status = 'leased' AND q.lease_expires_at < pg_catalog.now())
          ORDER BY q.created_at, q.id
          FOR UPDATE SKIP LOCKED
          LIMIT 1;

          IF NOT FOUND THEN
            RETURN NULL;
          END IF;

          UPDATE workflow.job_queue AS q
          SET status = 'leased',
              lease_owner = p_lease_owner,
              lease_expires_at = pg_catalog.now()
                + p_lease_seconds * interval '1 second',
              heartbeat_at = pg_catalog.now(),
              fencing_epoch = job.fencing_epoch + 1,
              attempt_id = gen_random_uuid()
          WHERE q.id = job.id
          RETURNING q.* INTO job;
          RETURN job;
        END;
        $$
        """
    )
    op.execute(
        "ALTER FUNCTION workflow.lease_next_job(text, integer) OWNER TO shiftmind_owner"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION workflow.lease_next_job(text, integer) FROM PUBLIC"
    )
    op.execute("GRANT USAGE ON SCHEMA workflow TO shiftmind_lease")
    op.execute("GRANT shiftmind_lease TO shiftmind_login")
    op.execute(
        "GRANT EXECUTE ON FUNCTION workflow.lease_next_job(text, integer) TO shiftmind_lease"
    )

    op.execute(
        """
        CREATE FUNCTION workflow.renew_job_lease(
          p_job_id uuid,
          p_fencing_epoch bigint,
          p_extension_seconds integer
        ) RETURNS boolean
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET search_path = pg_catalog, workflow
        AS $$
        DECLARE
          updated_count integer;
        BEGIN
          IF p_extension_seconds <= 0 THEN
            RAISE EXCEPTION 'lease extension must be positive' USING ERRCODE = '22023';
          END IF;
          UPDATE workflow.job_queue AS q
          SET lease_expires_at = pg_catalog.now()
                + p_extension_seconds * interval '1 second',
              heartbeat_at = pg_catalog.now()
          WHERE q.id = p_job_id
            AND q.status = 'leased'
            AND q.fencing_epoch = p_fencing_epoch;
          GET DIAGNOSTICS updated_count = ROW_COUNT;
          RETURN updated_count = 1;
        END;
        $$
        """
    )
    op.execute(
        "ALTER FUNCTION workflow.renew_job_lease(uuid, bigint, integer) OWNER TO shiftmind_owner"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION workflow.renew_job_lease(uuid, bigint, integer) FROM PUBLIC"
    )
    op.execute(
        "GRANT EXECUTE ON FUNCTION workflow.renew_job_lease(uuid, bigint, integer) TO shiftmind_runtime"
    )


def downgrade() -> None:
    op.execute(
        "REVOKE EXECUTE ON FUNCTION workflow.renew_job_lease(uuid, bigint, integer) FROM shiftmind_runtime"
    )
    op.execute(
        "REVOKE EXECUTE ON FUNCTION workflow.lease_next_job(text, integer) FROM shiftmind_lease"
    )
    op.execute("REVOKE shiftmind_lease FROM shiftmind_login")
    op.execute("REVOKE USAGE ON SCHEMA workflow FROM shiftmind_lease")
    op.execute(
        "DROP FUNCTION IF EXISTS workflow.renew_job_lease(uuid, bigint, integer)"
    )
    op.execute("DROP FUNCTION IF EXISTS workflow.lease_next_job(text, integer)")
    op.execute(
        "REVOKE UPDATE (status, heartbeat_at) ON workflow.job_queue FROM shiftmind_runtime"
    )
    op.execute("REVOKE SELECT, INSERT, UPDATE, DELETE ON workflow.job_queue FROM shiftmind_runtime")
    op.execute("REVOKE USAGE ON SCHEMA workflow FROM shiftmind_runtime")
    op.execute("DROP POLICY IF EXISTS job_queue_site_isolation ON workflow.job_queue")
    op.drop_table("job_queue", schema="workflow")
    op.execute("DROP SCHEMA workflow")
    op.execute(
        """
        DO $$
        BEGIN
          IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'shiftmind_lease') THEN
            BEGIN
              DROP ROLE shiftmind_lease;
            EXCEPTION
              WHEN dependent_objects_still_exist THEN NULL;
            END;
          END IF;
        END
        $$;
        """
    )
