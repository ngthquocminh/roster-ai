"""SQLAlchemy Core adapter for the site-scoped conversation aggregate."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Connection, func, insert, select, update

from adapters.postgres.schema import (
    agent_run,
    conversation,
    message,
    membership,
    persisted_event,
    scenario_version,
)
from application.contracts.activity import (
    ActivityItemV1,
    AgentResponseActivityV1,
    PlannerMessageActivityV1,
)
from application.contracts.persisted_event import PersistedEventV1
from application.ports.conversation import (
    AcceptedTurnV1,
    AgentRunNotQueuedError,
    ClaimedAgentRunV1,
    ConversationPageV1,
    ConversationTimelineV1,
    ConversationV1,
    ExecutedAgentRunV1,
)

# The conversation stream's identity IS the conversation's own UUID (AD-21).
# Reads filter on `stream_id` rather than the `conversation_id` correlation
# column so a future run-scoped stream on the same conversation cannot leak
# into this timeline under a sequence numbering that does not constrain it.
_PLANNER_MESSAGE = "planner_message"


class UnsupportedActivityPayloadError(ValueError):
    """A persisted event carries an activity variant this story cannot render.

    Seven of AD-20's eight discriminants are reserved names with no shipped
    payload shape. Reaching one means a later story wrote an event this reader
    predates — a typed failure, not a `KeyError` that takes the whole timeline
    down with it.
    """


class PostgresConversationRepository:
    def create(
        self,
        connection: Connection,
        *,
        scenario_id: UUID,
        scenario_version_id: UUID,
        site_id: UUID,
        actor_id: UUID,
    ) -> ConversationV1 | None:
        # Validate the caller's selection; never resolve "latest" here. The
        # catalogue reader orders versions by ordinal, so a second resolution
        # rule in this adapter would pin something other than what the planner
        # was shown — and AD-9's no-drift guarantee is empty if the initial
        # pin is arbitrary. RLS scopes both rows to the session's site.
        pinned = connection.execute(
            select(scenario_version.c.id).where(
                scenario_version.c.id == scenario_version_id,
                scenario_version.c.scenario_id == scenario_id,
            )
        ).scalar_one_or_none()
        if pinned is None:
            return None
        row = connection.execute(
            insert(conversation)
            .values(
                site_id=site_id,
                scenario_id=scenario_id,
                scenario_version_id=pinned,
                created_by_actor_id=actor_id,
            )
            .returning(conversation)
        ).one()
        return ConversationV1(
            row.id, row.scenario_id, row.scenario_version_id, row.resource_version
        )

    def list_for_scenario(
        self, connection: Connection, *, scenario_id: UUID, limit: int = 100
    ) -> ConversationPageV1:
        # Over-fetch by one: the extra row is the truncation signal and is
        # dropped before returning.
        rows = connection.execute(
            select(conversation)
            .where(conversation.c.scenario_id == scenario_id)
            .order_by(conversation.c.created_at.desc(), conversation.c.id.desc())
            .limit(limit + 1)
        ).all()
        has_more = len(rows) > limit
        return ConversationPageV1(
            tuple(
                ConversationV1(
                    r.id, r.scenario_id, r.scenario_version_id, r.resource_version
                )
                for r in rows[:limit]
            ),
            limit,
            has_more,
        )

    def timeline(
        self, connection: Connection, *, conversation_id: UUID, limit: int = 200
    ) -> ConversationTimelineV1 | None:
        conv = connection.execute(
            select(conversation).where(conversation.c.id == conversation_id)
        ).one_or_none()
        if conv is None:
            return None
        # Descending + reverse yields the newest `limit` events in ascending
        # order. Ordering ascending with a LIMIT would pin the window to the
        # head of the stream and hide every recent turn.
        rows = connection.execute(
            select(persisted_event)
            .where(persisted_event.c.stream_id == conversation_id)
            .order_by(persisted_event.c.sequence.desc())
            .limit(limit + 1)
        ).all()
        has_more = len(rows) > limit
        window = list(reversed(rows[:limit]))
        status = connection.execute(
            select(agent_run.c.status)
            .where(agent_run.c.conversation_id == conversation_id)
            .order_by(agent_run.c.created_at.desc(), agent_run.c.id.desc())
            .limit(1)
        ).scalar_one_or_none()
        return ConversationTimelineV1(
            conv.id,
            conv.resource_version,
            status,
            tuple(_event_from_row(r) for r in window),
            limit,
            has_more,
        )

    def events_after(
        self,
        connection: Connection,
        *,
        stream_id: UUID,
        after: Decimal,
        limit: int,
    ) -> tuple[PersistedEventV1, ...] | None:
        # The RLS-filtered conversation row is the visibility check: a stream
        # this site cannot see must answer `None`, indistinguishable from a
        # stream that does not exist. Reading the events alone would answer with
        # an empty tuple, which is a different and disclosing answer.
        visible = connection.execute(
            select(conversation.c.id).where(conversation.c.id == stream_id)
        ).scalar_one_or_none()
        if visible is None:
            return None
        # Ascending here, descending in `timeline()` — both are correct. The
        # timeline shows the newest window of an unbounded history; replay
        # drains forward from a cursor, so it must start at the oldest
        # outstanding event.
        rows = connection.execute(
            select(persisted_event)
            .where(
                persisted_event.c.stream_id == stream_id,
                persisted_event.c.sequence > after,
            )
            .order_by(persisted_event.c.sequence.asc())
            .limit(limit)
        ).all()
        return tuple(_event_from_row(r) for r in rows)

    def accept_turn(
        self,
        connection: Connection,
        *,
        conversation_id: UUID,
        site_id: UUID,
        actor_id: UUID,
        text: str,
        request_id: UUID,
    ) -> AcceptedTurnV1 | None:
        # `FOR UPDATE` on the RLS-filtered conversation row is the whole
        # serialization mechanism. A prior advisory lock would be taken before
        # the site check — cluster-global, not RLS-scoped — letting one site
        # block another's conversation and turning lock latency into an
        # existence oracle for a foreign UUID.
        conv = connection.execute(
            select(conversation)
            .where(conversation.c.id == conversation_id)
            .with_for_update()
        ).one_or_none()
        if conv is None:
            return None
        new_version = conv.resource_version + 1
        msg_id, run_id, activity_id = uuid4(), uuid4(), uuid4()
        msg = connection.execute(
            insert(message)
            .values(
                id=msg_id,
                site_id=site_id,
                conversation_id=conversation_id,
                actor_id=actor_id,
                text=text,
            )
            .returning(message.c.created_at)
        ).one()
        connection.execute(
            insert(agent_run).values(
                id=run_id,
                site_id=site_id,
                conversation_id=conversation_id,
                message_id=msg_id,
                status="agent_queued",
            )
        )
        sequence = connection.execute(
            select(
                func.coalesce(func.max(persisted_event.c.sequence), Decimal(0)) + 1
            ).where(persisted_event.c.stream_id == conversation_id)
        ).scalar_one()
        occurred_at = msg.created_at
        event = PersistedEventV1(
            stream_id=conversation_id,
            sequence=sequence,
            event_type="planner_message_accepted",
            occurred_at=occurred_at,
            resource_version=new_version,
            request_id=request_id,
            conversation_id=conversation_id,
            agent_run_id=run_id,
            site_id=site_id,
            actor_id=actor_id,
            payload=PlannerMessageActivityV1(
                activity_id=activity_id,
                activity_type=_PLANNER_MESSAGE,
                conversation_id=conversation_id,
                conversation_resource_version=new_version,
                scenario_id=conv.scenario_id,
                scenario_version_id=conv.scenario_version_id,
                occurred_at=occurred_at,
                message_id=msg_id,
                text=text,
            ),
        )
        connection.execute(
            insert(persisted_event).values(
                id=activity_id,
                site_id=site_id,
                stream_id=event.stream_id,
                sequence=event.sequence,
                event_type=event.event_type,
                resource_version=event.resource_version,
                request_id=event.request_id,
                conversation_id=event.conversation_id,
                agent_run_id=event.agent_run_id,
                actor_id=event.actor_id,
                occurred_at=event.occurred_at,
                payload=_payload_to_json(event.payload),
            )
        )
        connection.execute(
            update(conversation)
            .where(conversation.c.id == conversation_id)
            .values(resource_version=new_version)
        )
        return AcceptedTurnV1(event, new_version, "agent_queued")

    def claim_queued_run(
        self,
        connection: Connection,
        *,
        conversation_id: UUID,
        agent_run_id: UUID,
    ) -> ClaimedAgentRunV1 | None:
        row = connection.execute(
            select(
                agent_run.c.id.label("agent_run_id"),
                agent_run.c.status,
                conversation.c.id.label("conversation_id"),
                conversation.c.scenario_id,
                conversation.c.scenario_version_id,
                conversation.c.site_id,
                message.c.actor_id,
                message.c.text.label("prompt"),
                membership.c.id.label("membership_id"),
            )
            .join(conversation, conversation.c.id == agent_run.c.conversation_id)
            .join(message, message.c.id == agent_run.c.message_id)
            .join(
                membership,
                (membership.c.app_user_id == message.c.actor_id)
                & (membership.c.site_id == conversation.c.site_id)
                & membership.c.revoked_at.is_(None),
            )
            .where(
                conversation.c.id == conversation_id,
                agent_run.c.id == agent_run_id,
            )
            .with_for_update(of=agent_run)
        ).one_or_none()
        if row is None:
            return None
        if row.status != "agent_queued":
            raise AgentRunNotQueuedError("agent run is not queued")
        connection.execute(
            update(agent_run)
            .where(agent_run.c.id == agent_run_id)
            .values(status="agent_running")
        )
        history_rows = connection.execute(
            select(persisted_event)
            .where(
                persisted_event.c.stream_id == conversation_id,
                # Exclude only this run's own events. `agent_run_id` is
                # NOT NULL with a composite FK (`schema.py`), so no row can
                # carry SQL NULL here and `!=` cannot silently drop one -- an
                # earlier `or_(... is_(None), ...)` guard against that was
                # unreachable and its comment described a defect the schema
                # forbids.
                persisted_event.c.agent_run_id != agent_run_id,
            )
            .order_by(persisted_event.c.sequence.desc())
            .limit(100)
        ).all()
        return ClaimedAgentRunV1(
            agent_run_id=row.agent_run_id,
            conversation_id=row.conversation_id,
            scenario_id=row.scenario_id,
            scenario_version_id=row.scenario_version_id,
            site_id=row.site_id,
            actor_id=row.actor_id,
            membership_id=row.membership_id,
            prompt=row.prompt,
            history=tuple(
                _event_from_row(item).payload for item in reversed(history_rows)
            ),
        )

    def finish_agent_run(
        self,
        connection: Connection,
        *,
        claimed: ClaimedAgentRunV1,
        status: str,
        response,
        request_id: UUID,
    ) -> ExecutedAgentRunV1:
        conv = connection.execute(
            select(conversation)
            .where(conversation.c.id == claimed.conversation_id)
            .with_for_update()
        ).one_or_none()
        if conv is None:
            raise RuntimeError("claimed conversation is no longer visible")
        current = connection.execute(
            select(agent_run.c.status)
            .where(agent_run.c.id == claimed.agent_run_id)
            .with_for_update()
        ).scalar_one_or_none()
        if current != "agent_running":
            raise AgentRunNotQueuedError("agent run is no longer running")
        new_version = conv.resource_version + 1
        activity_id = uuid4()
        occurred_at = datetime.now(timezone.utc)
        sequence = connection.execute(
            select(
                func.coalesce(func.max(persisted_event.c.sequence), Decimal(0)) + 1
            ).where(persisted_event.c.stream_id == claimed.conversation_id)
        ).scalar_one()
        payload = AgentResponseActivityV1(
            activity_id=activity_id,
            activity_type="agent_response",
            conversation_id=claimed.conversation_id,
            conversation_resource_version=new_version,
            scenario_id=claimed.scenario_id,
            scenario_version_id=claimed.scenario_version_id,
            occurred_at=occurred_at,
            response=response,
        )
        event = PersistedEventV1(
            stream_id=claimed.conversation_id,
            sequence=sequence,
            event_type="agent_response",
            occurred_at=occurred_at,
            resource_version=new_version,
            request_id=request_id,
            conversation_id=claimed.conversation_id,
            agent_run_id=claimed.agent_run_id,
            site_id=claimed.site_id,
            actor_id=claimed.actor_id,
            payload=payload,
        )
        connection.execute(
            update(agent_run)
            .where(agent_run.c.id == claimed.agent_run_id)
            .values(status=status)
        )
        connection.execute(
            insert(persisted_event).values(
                id=activity_id,
                site_id=claimed.site_id,
                stream_id=event.stream_id,
                sequence=event.sequence,
                event_type=event.event_type,
                resource_version=event.resource_version,
                request_id=event.request_id,
                conversation_id=event.conversation_id,
                agent_run_id=event.agent_run_id,
                actor_id=event.actor_id,
                occurred_at=event.occurred_at,
                payload=_payload_to_json(payload),
            )
        )
        connection.execute(
            update(conversation)
            .where(conversation.c.id == claimed.conversation_id)
            .values(resource_version=new_version)
        )
        return ExecutedAgentRunV1(event, new_version, status)


def _payload_to_json(activity: ActivityItemV1) -> dict:
    common = {
        "schema_version": activity.schema_version,
        "activity_id": str(activity.activity_id),
        "activity_type": activity.activity_type,
        "conversation_id": str(activity.conversation_id),
        "conversation_resource_version": activity.conversation_resource_version,
        "scenario_id": str(activity.scenario_id),
        "scenario_version_id": str(activity.scenario_version_id),
        "occurred_at": activity.occurred_at.isoformat(),
    }
    if isinstance(activity, PlannerMessageActivityV1):
        return {
            **common,
            "message_id": str(activity.message_id),
            "text": activity.text,
        }
    from pydantic import TypeAdapter
    return {
        **common,
        "response": TypeAdapter(type(activity.response)).dump_python(
            activity.response, mode="json"
        ),
    }


def _activity_from_payload(value: dict) -> ActivityItemV1:
    activity_type = value.get("activity_type")
    if activity_type not in (_PLANNER_MESSAGE, "agent_response"):
        raise UnsupportedActivityPayloadError(
            f"activity_type {activity_type!r} has no payload shape in this reader"
        )
    common = dict(
        activity_id=UUID(value["activity_id"]),
        activity_type=activity_type,
        conversation_id=UUID(value["conversation_id"]),
        conversation_resource_version=value["conversation_resource_version"],
        scenario_id=UUID(value["scenario_id"]),
        scenario_version_id=UUID(value["scenario_version_id"]),
        occurred_at=datetime.fromisoformat(value["occurred_at"]).astimezone(
            timezone.utc
        ),
        schema_version=value["schema_version"],
    )
    if activity_type == _PLANNER_MESSAGE:
        return PlannerMessageActivityV1(
            **common,
            message_id=UUID(value["message_id"]),
            text=value["text"],
        )
    from pydantic import TypeAdapter
    from application.contracts.grounding import GroundedResponseV1
    return AgentResponseActivityV1(
        **common,
        response=TypeAdapter(GroundedResponseV1).validate_python(value["response"]),
    )


def _event_from_row(row) -> PersistedEventV1:
    return PersistedEventV1(
        stream_id=row.stream_id,
        sequence=row.sequence,
        event_type=row.event_type,
        occurred_at=row.occurred_at,
        resource_version=row.resource_version,
        request_id=row.request_id,
        conversation_id=row.conversation_id,
        agent_run_id=row.agent_run_id,
        site_id=row.site_id,
        actor_id=row.actor_id,
        payload=_activity_from_payload(row.payload),
    )
