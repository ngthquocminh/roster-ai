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
)

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
