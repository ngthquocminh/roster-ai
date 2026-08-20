"""SQLAlchemy metadata for Story 1.1's governed PostgreSQL history."""
from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    MetaData,
    Numeric,
    String,
    Table,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID


metadata = MetaData()


def _id_column() -> Column:
    return Column(
        "id",
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _site_id_column() -> Column:
    return Column(
        "site_id",
        UUID(as_uuid=True),
        ForeignKey("site.id", ondelete="RESTRICT"),
        nullable=False,
    )


organization = Table(
    "organization",
    metadata,
    _id_column(),
    Column("name", String(200), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

site = Table(
    "site",
    metadata,
    _id_column(),
    Column(
        "organization_id",
        UUID(as_uuid=True),
        ForeignKey("organization.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("name", String(200), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
)

scenario = Table(
    "scenario",
    metadata,
    _id_column(),
    _site_id_column(),
    Column("fixture_id", String(200), nullable=False),
    Column("name", String(200), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    UniqueConstraint("site_id", "fixture_id", name="uq_scenario_site_fixture"),
    UniqueConstraint("id", "site_id", name="uq_scenario_id_site"),
)

scenario_version = Table(
    "scenario_version",
    metadata,
    _id_column(),
    _site_id_column(),
    Column("scenario_id", UUID(as_uuid=True), nullable=False),
    Column("fixture_id", String(200), nullable=False),
    Column("version", String(100), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column(
        "checksum_algorithm",
        String(20),
        nullable=False,
        server_default=text("'sha256'"),
    ),
    Column(
        "checksum_schema_version",
        String(40),
        nullable=False,
        server_default=text("'rfc8785-v1'"),
    ),
    Column("checksum_digest", String(64), nullable=False),
    Column(
        "imported_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    ForeignKeyConstraint(
        ["scenario_id", "site_id"],
        ["scenario.id", "scenario.site_id"],
        name="fk_scenario_version_scenario_site",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "site_id",
        "fixture_id",
        "version",
        name="uq_scenario_version_site_fixture_version",
    ),
    UniqueConstraint("id", "site_id", name="uq_scenario_version_id_site"),
    CheckConstraint(
        "checksum_algorithm = 'sha256'",
        name="ck_scenario_version_checksum_algorithm",
    ),
    CheckConstraint(
        "checksum_schema_version = 'rfc8785-v1'",
        name="ck_scenario_version_checksum_schema_version",
    ),
    CheckConstraint(
        "checksum_digest ~ '^[0-9a-f]{64}$'",
        name="ck_scenario_version_checksum_digest",
    ),
)

fixture_lineage = Table(
    "fixture_lineage",
    metadata,
    _id_column(),
    _site_id_column(),
    Column("scenario_version_id", UUID(as_uuid=True), nullable=False),
    Column("source_package", String(200), nullable=False),
    Column("source_path", Text, nullable=False),
    Column(
        "imported_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    ForeignKeyConstraint(
        ["scenario_version_id", "site_id"],
        ["scenario_version.id", "scenario_version.site_id"],
        name="fk_fixture_lineage_version_site",
        ondelete="RESTRICT",
    ),
    UniqueConstraint(
        "site_id",
        "scenario_version_id",
        name="uq_fixture_lineage_version_site",
    ),
)

evidence_reference = Table(
    "evidence_reference",
    metadata,
    _id_column(),
    _site_id_column(),
    Column("scenario_version_id", UUID(as_uuid=True), nullable=False),
    Column("reference_type", String(80), nullable=False),
    Column("reference_value", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    ForeignKeyConstraint(
        ["scenario_version_id", "site_id"],
        ["scenario_version.id", "scenario_version.site_id"],
        name="fk_evidence_reference_version_site",
        ondelete="RESTRICT",
    ),
)

app_user = Table(
    "app_user",
    metadata,
    _id_column(),
    Column("idp_subject", String(255), nullable=False, unique=True),
    Column("email", String(320), nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("disabled_at", DateTime(timezone=True), nullable=True),
)
Index(
    "uq_app_user_singleton",
    text("(true)"),
    unique=True,
    _table=app_user,
)

membership = Table(
    "membership",
    metadata,
    _id_column(),
    Column(
        "app_user_id",
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    _site_id_column(),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
)
Index(
    "uq_membership_single_active",
    text("(true)"),
    unique=True,
    postgresql_where=membership.c.revoked_at.is_(None),
    _table=membership,
)

session_index = Table(
    "session_index",
    metadata,
    _id_column(),
    Column("session_token_hash", String(64), nullable=False, unique=True),
    Column("csrf_token_hash", String(64), nullable=False),
    Column(
        "app_user_id",
        UUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    ),
    Column(
        "site_id",
        UUID(as_uuid=True),
        ForeignKey("site.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("revoked_at", DateTime(timezone=True), nullable=True),
    schema="auth",
)

conversation = Table(
    "conversation", metadata, _id_column(), _site_id_column(),
    Column("scenario_id", UUID(as_uuid=True), nullable=False),
    Column("scenario_version_id", UUID(as_uuid=True), nullable=False),
    Column("created_by_actor_id", UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
    Column("resource_version", BigInteger, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_conversation_scenario_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_conversation_version_site", ondelete="RESTRICT"),
    UniqueConstraint("id", "site_id", name="uq_conversation_id_site"),
)

message = Table(
    "message", metadata, _id_column(), _site_id_column(),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("actor_id", UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
    Column("text", Text, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_message_conversation_site", ondelete="RESTRICT"),
    UniqueConstraint("id", "site_id", name="uq_message_id_site"),
    CheckConstraint("length(btrim(text)) > 0", name="ck_message_text_nonempty"),
)

agent_run = Table(
    "agent_run", metadata, _id_column(), _site_id_column(),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("message_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(40), nullable=False, server_default=text("'agent_queued'")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_agent_run_conversation_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["message_id", "site_id"], ["message.id", "message.site_id"], name="fk_agent_run_message_site", ondelete="RESTRICT"),
    UniqueConstraint("id", "site_id", name="uq_agent_run_id_site"),
    CheckConstraint("status IN ('agent_queued','agent_running','approval_required','agent_completed','agent_timed_out','agent_cancelled','agent_failed')", name="ck_agent_run_status"),
)

persisted_event = Table(
    "persisted_event", metadata, _id_column(), _site_id_column(),
    Column("stream_id", UUID(as_uuid=True), nullable=False),
    Column("sequence", Numeric(38, 0, asdecimal=True), nullable=False),
    Column("event_type", String(100), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("resource_version", BigInteger, nullable=False),
    Column("request_id", UUID(as_uuid=True), nullable=False),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("agent_run_id", UUID(as_uuid=True), nullable=False),
    Column("actor_id", UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
    Column("payload", JSONB, nullable=False),
    ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_persisted_event_conversation_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["agent_run_id", "site_id"], ["agent_run.id", "agent_run.site_id"], name="fk_persisted_event_agent_run_site", ondelete="RESTRICT"),
    UniqueConstraint("stream_id", "sequence", name="uq_persisted_event_stream_sequence"),
    UniqueConstraint("id", "site_id", name="uq_persisted_event_id_site"),
    # A conversation stream's identity IS the conversation's UUID (AD-21), so a
    # second stream cannot be numbered against the same conversation and
    # collide inside one rendered timeline.
    CheckConstraint("stream_id = conversation_id", name="ck_persisted_event_stream_is_conversation"),
)

# Indexes for this aggregate's reads and for the site_id predicate that FORCE
# RLS evaluates on every row of every query against these tables.
Index("ix_conversation_site_id", conversation.c.site_id)
Index("ix_message_site_id", message.c.site_id)
Index("ix_agent_run_site_id", agent_run.c.site_id)
Index("ix_persisted_event_site_id", persisted_event.c.site_id)
Index("ix_conversation_scenario_id", conversation.c.scenario_id)
Index("ix_message_conversation_id", message.c.conversation_id)
Index("ix_agent_run_conversation_created", agent_run.c.conversation_id, agent_run.c.created_at)
Index("ix_persisted_event_conversation_id", persisted_event.c.conversation_id)

proposal = Table(
    "proposal", metadata, _id_column(), _site_id_column(),
    Column("scenario_id", UUID(as_uuid=True), nullable=False),
    Column("scenario_version_id", UUID(as_uuid=True), nullable=False),
    Column("conversation_id", UUID(as_uuid=True), nullable=False),
    Column("created_by_actor_id", UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
    Column("state", String(20), nullable=False, server_default=text("'active'")),
    Column("current_version_id", UUID(as_uuid=True), nullable=True),
    Column("resource_version", BigInteger, nullable=False, server_default=text("1")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_proposal_scenario_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_proposal_scenario_version_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["conversation_id", "site_id"], ["conversation.id", "conversation.site_id"], name="fk_proposal_conversation_site", ondelete="RESTRICT"),
    UniqueConstraint("id", "site_id", name="uq_proposal_id_site"),
    CheckConstraint("state IN ('active','rejected')", name="ck_proposal_state"),
)

proposal_version = Table(
    "proposal_version", metadata, _id_column(), _site_id_column(),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("version_ordinal", BigInteger, nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("canonical_hash", String(64), nullable=False),
    Column("checksum_algorithm", String(20), nullable=False, server_default=text("'sha256'")),
    Column("checksum_schema_version", String(40), nullable=False, server_default=text("'rfc8785-v1'")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    ForeignKeyConstraint(["proposal_id", "site_id"], ["proposal.id", "proposal.site_id"], name="fk_proposal_version_proposal_site", ondelete="RESTRICT"),
    UniqueConstraint("proposal_id", "version_ordinal", name="uq_proposal_version_ordinal"),
    UniqueConstraint("id", "site_id", name="uq_proposal_version_id_site"),
    CheckConstraint("checksum_algorithm = 'sha256'", name="ck_proposal_version_checksum_algorithm"),
    CheckConstraint("checksum_schema_version = 'rfc8785-v1'", name="ck_proposal_version_checksum_schema_version"),
    CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_proposal_version_canonical_hash"),
)
proposal.append_constraint(
    ForeignKeyConstraint(
        ["current_version_id", "site_id"],
        ["proposal_version.id", "proposal_version.site_id"],
        name="fk_proposal_current_version_site",
        ondelete="RESTRICT",
        use_alter=True,
    )
)

command_idempotency = Table(
    "command_idempotency", metadata, _id_column(), _site_id_column(),
    Column("actor_id", UUID(as_uuid=True), ForeignKey("app_user.id", ondelete="RESTRICT"), nullable=False),
    Column("operation", String(100), nullable=False),
    Column("idempotency_key", String(40), nullable=False),
    Column("body_hash", String(64), nullable=False),
    Column("response_payload", JSONB, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    # AD-8: one effect per (actor, site, operation, key). The body hash stays
    # out of the key so that reusing a key with a different body collides here
    # instead of inserting a second, indistinguishable row.
    UniqueConstraint("site_id", "actor_id", "operation", "idempotency_key", name="uq_command_idempotency_request"),
    UniqueConstraint("id", "site_id", name="uq_command_idempotency_id_site"),
    CheckConstraint("body_hash ~ '^[0-9a-f]{64}$'", name="ck_command_idempotency_body_hash"),
)

Index("ix_proposal_site_id", proposal.c.site_id)
Index("ix_proposal_version_site_id", proposal_version.c.site_id)
Index("ix_command_idempotency_site_id", command_idempotency.c.site_id)
Index("ix_proposal_conversation_id", proposal.c.conversation_id)
Index("ix_proposal_version_proposal_id", proposal_version.c.proposal_id)
Index("ix_command_idempotency_actor_operation", command_idempotency.c.actor_id, command_idempotency.c.operation)

run_snapshot = Table(
    "run_snapshot", metadata, _id_column(), _site_id_column(),
    Column("scenario_id", UUID(as_uuid=True), nullable=False),
    Column("scenario_version_id", UUID(as_uuid=True), nullable=False),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("proposal_version_id", UUID(as_uuid=True), nullable=False),
    Column("baseline_schedule_version", String(100), nullable=True),
    Column("payload", JSONB, nullable=False),
    Column("canonical_hash", String(64), nullable=False),
    Column("checksum_algorithm", String(20), nullable=False, server_default=text("'sha256'")),
    Column("checksum_schema_version", String(40), nullable=False, server_default=text("'rfc8785-v1'")),
    Column("accepted_at", DateTime(timezone=True), nullable=False),
    ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_run_snapshot_scenario_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_run_snapshot_scenario_version_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["proposal_id", "site_id"], ["proposal.id", "proposal.site_id"], name="fk_run_snapshot_proposal_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["proposal_version_id", "site_id"], ["proposal_version.id", "proposal_version.site_id"], name="fk_run_snapshot_proposal_version_site", ondelete="RESTRICT"),
    UniqueConstraint("id", "site_id", name="uq_run_snapshot_id_site"),
    CheckConstraint("checksum_algorithm = 'sha256'", name="ck_run_snapshot_checksum_algorithm"),
    CheckConstraint("checksum_schema_version = 'rfc8785-v1'", name="ck_run_snapshot_checksum_schema_version"),
    CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_run_snapshot_canonical_hash"),
)

schedule_run = Table(
    "schedule_run", metadata, _id_column(), _site_id_column(),
    Column("run_snapshot_id", UUID(as_uuid=True), nullable=False),
    Column("status", String(40), nullable=False, server_default=text("'solver_queued'")),
    Column("reason", String(100), nullable=True),
    Column("candidate_schedule_version_id", UUID(as_uuid=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    Column("finished_at", DateTime(timezone=True), nullable=True),
    ForeignKeyConstraint(["run_snapshot_id", "site_id"], ["run_snapshot.id", "run_snapshot.site_id"], name="fk_schedule_run_snapshot_site", ondelete="RESTRICT"),
    UniqueConstraint("id", "site_id", name="uq_schedule_run_id_site"),
    CheckConstraint("status IN ('solver_queued','solver_running','cancellation_requested','solver_completed','solver_infeasible','solver_timed_out','solver_cancelled','solver_failed')", name="ck_schedule_run_status"),
    CheckConstraint("candidate_schedule_version_id IS NULL OR status = 'solver_completed'", name="ck_schedule_run_candidate_completed"),
)

schedule_version = Table(
    "schedule_version", metadata, _id_column(), _site_id_column(),
    Column("schedule_run_id", UUID(as_uuid=True), nullable=False),
    Column("scenario_id", UUID(as_uuid=True), nullable=False),
    Column("scenario_version_id", UUID(as_uuid=True), nullable=False),
    Column("proposal_id", UUID(as_uuid=True), nullable=False),
    Column("proposal_version_id", UUID(as_uuid=True), nullable=False),
    Column("solver_status", String(20), nullable=False),
    Column("payload", JSONB, nullable=False),
    Column("canonical_hash", String(64), nullable=False),
    Column("checksum_algorithm", String(20), nullable=False, server_default=text("'sha256'")),
    Column("checksum_schema_version", String(40), nullable=False, server_default=text("'rfc8785-v1'")),
    Column("created_at", DateTime(timezone=True), nullable=False, server_default=text("CURRENT_TIMESTAMP")),
    ForeignKeyConstraint(["schedule_run_id", "site_id"], ["schedule_run.id", "schedule_run.site_id"], name="fk_schedule_version_run_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["scenario_id", "site_id"], ["scenario.id", "scenario.site_id"], name="fk_schedule_version_scenario_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["scenario_version_id", "site_id"], ["scenario_version.id", "scenario_version.site_id"], name="fk_schedule_version_scenario_version_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["proposal_id", "site_id"], ["proposal.id", "proposal.site_id"], name="fk_schedule_version_proposal_site", ondelete="RESTRICT"),
    ForeignKeyConstraint(["proposal_version_id", "site_id"], ["proposal_version.id", "proposal_version.site_id"], name="fk_schedule_version_proposal_version_site", ondelete="RESTRICT"),
    UniqueConstraint("schedule_run_id", name="uq_schedule_version_run"),
    UniqueConstraint("id", "site_id", name="uq_schedule_version_id_site"),
    CheckConstraint("solver_status IN ('OPTIMAL','FEASIBLE')", name="ck_schedule_version_feasible_status"),
    CheckConstraint("checksum_algorithm = 'sha256'", name="ck_schedule_version_checksum_algorithm"),
    CheckConstraint("checksum_schema_version = 'rfc8785-v1'", name="ck_schedule_version_checksum_schema_version"),
    CheckConstraint("canonical_hash ~ '^[0-9a-f]{64}$'", name="ck_schedule_version_canonical_hash"),
)
schedule_run.append_constraint(
    ForeignKeyConstraint(
        ["candidate_schedule_version_id", "site_id"],
        ["schedule_version.id", "schedule_version.site_id"],
        name="fk_schedule_run_candidate_site",
        ondelete="RESTRICT",
        use_alter=True,
    )
)

schedule_assignment = Table(
    "schedule_assignment", metadata, _id_column(), _site_id_column(),
    Column("schedule_version_id", UUID(as_uuid=True), nullable=False),
    Column("assignment_record_id", String(200), nullable=False),
    Column("worker_id", String(200), nullable=False),
    Column("task_id", String(200), nullable=False),
    Column("shift_id", String(200), nullable=True),
    Column("start_minute", BigInteger, nullable=False),
    Column("end_minute", BigInteger, nullable=False),
    Column("qualification_refs", JSONB, nullable=False, server_default=text("'[]'::jsonb")),
    Column("source", String(40), nullable=False),
    Column("lock_ref", String(200), nullable=True),
    ForeignKeyConstraint(["schedule_version_id", "site_id"], ["schedule_version.id", "schedule_version.site_id"], name="fk_schedule_assignment_version_site", ondelete="RESTRICT"),
    UniqueConstraint("schedule_version_id", "assignment_record_id", name="uq_schedule_assignment_record"),
    UniqueConstraint("id", "site_id", name="uq_schedule_assignment_id_site"),
    CheckConstraint("start_minute >= 0 AND end_minute > start_minute", name="ck_schedule_assignment_interval"),
)

for _table in (run_snapshot, schedule_run, schedule_version, schedule_assignment):
    Index(f"ix_{_table.name}_site_id", _table.c.site_id)
Index("ix_schedule_run_snapshot_id", schedule_run.c.run_snapshot_id)
Index("ix_schedule_version_run_id", schedule_version.c.schedule_run_id)
Index("ix_schedule_assignment_version_id", schedule_assignment.c.schedule_version_id)

login_handshake = Table(
    "login_handshake",
    metadata,
    _id_column(),
    Column("state", String(128), nullable=False, unique=True),
    Column("nonce", String(128), nullable=False),
    Column("code_verifier", String(128), nullable=False),
    Column("redirect_target", Text, nullable=False),
    Column(
        "created_at",
        DateTime(timezone=True),
        nullable=False,
        server_default=text("CURRENT_TIMESTAMP"),
    ),
    Column("expires_at", DateTime(timezone=True), nullable=False),
    Column("consumed_at", DateTime(timezone=True), nullable=True),
    schema="auth",
)
