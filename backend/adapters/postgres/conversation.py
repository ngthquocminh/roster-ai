"""SQLAlchemy Core adapter for the site-scoped conversation aggregate."""
from __future__ import annotations

from datetime import timezone
from decimal import Decimal
from typing import Callable
from uuid import UUID, uuid4

from sqlalchemy import Connection, func, insert, select, update

from adapters.postgres.schema import agent_run, conversation, message, persisted_event, scenario_version
from application.contracts.activity import ActivityItemV1
from application.ports.conversation import AcceptedTurnV1, ConversationTimelineV1, ConversationV1


class PostgresConversationRepository:
    def create(self, connection: Connection, *, scenario_id: UUID, site_id: UUID, actor_id: UUID) -> ConversationV1 | None:
        version_id = connection.execute(select(scenario_version.c.id).where(scenario_version.c.scenario_id == scenario_id).order_by(scenario_version.c.imported_at.desc()).limit(1)).scalar_one_or_none()
        if version_id is None:
            return None
        row = connection.execute(insert(conversation).values(site_id=site_id, scenario_id=scenario_id, scenario_version_id=version_id, created_by_actor_id=actor_id).returning(conversation)).one()
        return ConversationV1(row.id, row.scenario_id, row.scenario_version_id, row.resource_version)

    def list_for_scenario(self, connection: Connection, *, scenario_id: UUID, limit: int = 100) -> tuple[ConversationV1, ...]:
        rows = connection.execute(select(conversation).where(conversation.c.scenario_id == scenario_id).order_by(conversation.c.created_at.desc(), conversation.c.id).limit(limit))
        return tuple(ConversationV1(r.id, r.scenario_id, r.scenario_version_id, r.resource_version) for r in rows)

    def timeline(self, connection: Connection, *, conversation_id: UUID, limit: int = 200) -> ConversationTimelineV1 | None:
        conv = connection.execute(select(conversation).where(conversation.c.id == conversation_id)).one_or_none()
        if conv is None:
            return None
        rows = connection.execute(select(persisted_event).where(persisted_event.c.conversation_id == conversation_id).order_by(persisted_event.c.sequence.asc()).limit(limit)).all()
        status = connection.execute(select(agent_run.c.status).where(agent_run.c.conversation_id == conversation_id).order_by(agent_run.c.created_at.desc(), agent_run.c.id.desc()).limit(1)).scalar_one_or_none()
        items = tuple(_activity_from_payload(r.payload) for r in rows)
        return ConversationTimelineV1(conv.id, conv.resource_version, status, items, limit)

    def accept_turn(self, connection: Connection, *, conversation_id: UUID, site_id: UUID, actor_id: UUID, text: str, request_id: UUID, after_message: Callable[[], None] | None = None) -> AcceptedTurnV1 | None:
        connection.exec_driver_sql("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (str(conversation_id),))
        conv = connection.execute(select(conversation).where(conversation.c.id == conversation_id).with_for_update()).one_or_none()
        if conv is None:
            return None
        new_version = conv.resource_version + 1
        msg_id, run_id, activity_id = uuid4(), uuid4(), uuid4()
        msg = connection.execute(insert(message).values(id=msg_id, site_id=site_id, conversation_id=conversation_id, actor_id=actor_id, text=text).returning(message.c.created_at)).one()
        if after_message is not None:
            after_message()
        connection.execute(insert(agent_run).values(id=run_id, site_id=site_id, conversation_id=conversation_id, message_id=msg_id, status="agent_queued"))
        sequence = connection.execute(select(func.coalesce(func.max(persisted_event.c.sequence), Decimal(0)) + 1).where(persisted_event.c.stream_id == conversation_id)).scalar_one()
        payload = {"schema_version": "1", "activity_id": str(activity_id), "activity_type": "planner_message", "conversation_id": str(conversation_id), "conversation_resource_version": new_version, "scenario_id": str(conv.scenario_id), "scenario_version_id": str(conv.scenario_version_id), "occurred_at": msg.created_at.isoformat(), "message_id": str(msg_id), "text": text}
        connection.execute(insert(persisted_event).values(id=activity_id, site_id=site_id, stream_id=conversation_id, sequence=sequence, event_type="planner_message_accepted", resource_version=new_version, request_id=request_id, conversation_id=conversation_id, agent_run_id=run_id, actor_id=actor_id, payload=payload))
        connection.execute(update(conversation).where(conversation.c.id == conversation_id).values(resource_version=new_version))
        return AcceptedTurnV1(_activity_from_payload(payload), new_version, "agent_queued", str(sequence))


def _activity_from_payload(value: dict) -> ActivityItemV1:
    from datetime import datetime
    return ActivityItemV1(activity_id=UUID(value["activity_id"]), activity_type=value["activity_type"], conversation_id=UUID(value["conversation_id"]), conversation_resource_version=value["conversation_resource_version"], scenario_id=UUID(value["scenario_id"]), scenario_version_id=UUID(value["scenario_version_id"]), occurred_at=datetime.fromisoformat(value["occurred_at"]).astimezone(timezone.utc), message_id=UUID(value["message_id"]), text=value["text"], schema_version=value["schema_version"])
