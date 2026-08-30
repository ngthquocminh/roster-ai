"""SQLAlchemy Core adapter for the site-scoped conversation aggregate."""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import Connection, func, insert, or_, select, update

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
    ApprovalRequestActivityV1,
    ClarificationActivityV1,
    DraftActivityV1,
    DraftReferenceV1,
    PlannerMessageActivityV1,
    TerminalOutcomeActivityV1,
)
from application.contracts.dialogue import ResolvedClarificationV1, TerminalOutcomeV1
from application.contracts.grounding import GroundedResponseV1
from application.contracts.persisted_event import PersistedEventV1
from application.contracts.approval_binding import ApprovalBindingV1
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


#: EAD-5's closed vocabulary, mirroring `ck_agent_run_status_reason`
#: (`schema.py`). Approval outcomes are the only path into `agent_cancelled`
#: (ADR-4 D6); this set is what keeps `cancel_agent_run_for_approval` from
#: becoming a general cancellation API.
APPROVAL_CANCELLATION_REASONS = frozenset({"approval_rejected", "approval_expired", "approval_stale"})


class PostgresConversationRepository:
    def _append_approval_activity(self, connection: Connection, *, binding: ApprovalBindingV1, actor_id: UUID, request_id: UUID, agent_run_id: UUID | None, occurred_at: datetime | None = None, agent_run_status: str | None = None) -> ExecutedAgentRunV1:
        conv = connection.execute(select(conversation).where(conversation.c.id == binding.conversation_id).with_for_update()).one_or_none()
        if conv is None:
            raise RuntimeError("approval conversation is no longer visible")
        new_version = conv.resource_version + 1
        occurred_at = occurred_at or binding.created_at or datetime.now(timezone.utc)
        sequence = connection.execute(select(func.coalesce(func.max(persisted_event.c.sequence), Decimal(0)) + 1).where(persisted_event.c.stream_id == binding.conversation_id)).scalar_one()
        activity = ApprovalRequestActivityV1(
            activity_id=uuid4(), activity_type="approval_request", conversation_id=binding.conversation_id,
            conversation_resource_version=new_version, scenario_id=conv.scenario_id, scenario_version_id=conv.scenario_version_id,
            occurred_at=occurred_at, approval_id=binding.approval_id, approval_state=binding.state, agent_run_id=agent_run_id,
            schedule_run_id=binding.schedule_run_id, candidate_schedule_version_id=binding.candidate_schedule_version_id,
            baseline_schedule_version=binding.baseline_schedule_version, consequence_summary=binding.consequence_summary,
            parameter_hash=binding.parameter_hash, consequence_hash=binding.consequence_hash, policy_version=binding.policy_version,
            expires_at=binding.expires_at,
        )
        event = PersistedEventV1(stream_id=binding.conversation_id, sequence=sequence, event_type="approval_request", occurred_at=occurred_at, resource_version=new_version, request_id=request_id, conversation_id=binding.conversation_id, agent_run_id=agent_run_id, site_id=binding.site_id, actor_id=actor_id, payload=activity)
        connection.execute(insert(persisted_event).values(id=activity.activity_id, site_id=binding.site_id, stream_id=event.stream_id, sequence=event.sequence, event_type=event.event_type, resource_version=event.resource_version, request_id=event.request_id, conversation_id=event.conversation_id, agent_run_id=event.agent_run_id, actor_id=event.actor_id, occurred_at=event.occurred_at, payload=_payload_to_json(activity)))
        connection.execute(update(conversation).where(conversation.c.id == binding.conversation_id).values(resource_version=new_version))
        # `None`, never a fabricated "agent_completed": on the planner path there
        # is no agent run in scope, and the conversation may in fact have one
        # currently `agent_running`. The agent path's real status is written by
        # `pause_agent_run_for_approval`, which owns that transition.
        #
        # `agent_run_status` is explicit because the caller knows the status it
        # just wrote and this method does not. TX3 cancels the run BEFORE
        # appending its activity, so defaulting to "approval_required" here
        # reported a status the same transaction had already replaced.
        if agent_run_status is None and agent_run_id is not None:
            agent_run_status = "approval_required"
        return ExecutedAgentRunV1(event, new_version, agent_run_status)

    def pause_agent_run_for_approval(self, connection: Connection, *, claimed_agent_run_id: UUID, binding: ApprovalBindingV1, request_id: UUID) -> ExecutedAgentRunV1:
        # LOCK ORDER: conversation, THEN agent_run -- the same order
        # `finish_agent_run` takes. Locking `agent_run` first here (and reaching
        # `conversation` inside `_append_approval_activity`) is the textbook ABBA
        # shape against that method, and PostgreSQL resolves it by aborting one
        # transaction with a deadlock error that no handler catches.
        conv = connection.execute(select(conversation.c.id).where(conversation.c.id == binding.conversation_id).with_for_update()).one_or_none()
        if conv is None:
            raise RuntimeError("approval conversation is no longer visible")
        current = connection.execute(select(agent_run.c.status, agent_run.c.id).where(agent_run.c.id == claimed_agent_run_id).with_for_update()).one_or_none()
        if current is None or current.status != "agent_running":
            raise AgentRunNotQueuedError("agent run is no longer running")
        result = self._append_approval_activity(connection, binding=binding, actor_id=binding.initiated_by_actor_id, request_id=request_id, agent_run_id=claimed_agent_run_id, occurred_at=binding.created_at)
        connection.execute(update(agent_run).where(agent_run.c.id == claimed_agent_run_id).values(status="approval_required"))
        return ExecutedAgentRunV1(result.event, result.resource_version, "approval_required")

    def append_approval_request_activity(self, connection: Connection, *, binding: ApprovalBindingV1, actor_id: UUID, request_id: UUID, agent_run_id: UUID | None = None, occurred_at: datetime | None = None, agent_run_status: str | None = None) -> ExecutedAgentRunV1:
        return self._append_approval_activity(connection, binding=binding, actor_id=actor_id, request_id=request_id, agent_run_id=agent_run_id, occurred_at=occurred_at or binding.created_at, agent_run_status=agent_run_status)

    def cancel_agent_run_for_approval(self, connection: Connection, *, agent_run_id: UUID, binding: ApprovalBindingV1, reason: str) -> None:
        # LOCK ORDER: conversation, THEN agent_run. Approval terminalization is
        # deliberately the sole new path into cancellation, not a general API.
        if reason not in APPROVAL_CANCELLATION_REASONS:
            # Decision 6: this method accepts ONLY the three closed reasons.
            # `ck_agent_run_status_reason` would otherwise reject the write at
            # runtime as a database error rather than as a test failure, which
            # is exactly the shape Trap 3 warns about.
            raise ValueError(f"approval cancellation reason must be one of {sorted(APPROVAL_CANCELLATION_REASONS)}")
        conv = connection.execute(select(conversation.c.id).where(conversation.c.id == binding.conversation_id).with_for_update()).one_or_none()
        if conv is None:
            raise RuntimeError("approval conversation is no longer visible")
        current = connection.execute(select(agent_run.c.status).where(agent_run.c.id == agent_run_id).with_for_update()).one_or_none()
        if current is None or current.status != "approval_required":
            raise AgentRunNotQueuedError("agent run is no longer awaiting approval")
        connection.execute(update(agent_run).where(agent_run.c.id == agent_run_id).values(status="agent_cancelled", status_reason=reason))

    def latest_terminal_outcome_for_site(
        self,
        connection: Connection,
        *,
        site_id: UUID,
    ) -> PersistedEventV1 | None:
        row = connection.execute(
            select(persisted_event)
            .where(
                persisted_event.c.site_id == site_id,
                persisted_event.c.agent_run_id.is_not(None),
                persisted_event.c.event_type == "terminal_outcome",
            )
            .order_by(
                persisted_event.c.occurred_at.desc(),
                persisted_event.c.id.desc(),
            )
            .limit(1)
        ).one_or_none()
        return None if row is None else _event_from_row(row)

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
            select(agent_run.c.status, agent_run.c.status_reason)
            .where(agent_run.c.conversation_id == conversation_id)
            .order_by(agent_run.c.created_at.desc(), agent_run.c.id.desc())
            .limit(1)
        ).one_or_none()
        return ConversationTimelineV1(
            conv.id,
            conv.resource_version,
            status.status if status else None,
            tuple(_event_from_row(r) for r in window),
            limit,
            has_more,
            status.status_reason if status else None,
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
                # Exclude only this run's own events. `agent_run_id` was
                # NOT NULL when the guard below was removed as unreachable --
                # Story 3.5 widened it to nullable so a schedule-run stream
                # could omit it, and `ck_persisted_event_stream_owner`
                # constrains only `conversation_id`/`schedule_run_id`. A bare
                # `!=` evaluates to SQL NULL against a NULL row and would drop
                # it from this window silently, so the NULL branch is explicit
                # again rather than resting on an invariant that no longer
                # holds.
                or_(
                    persisted_event.c.agent_run_id.is_(None),
                    persisted_event.c.agent_run_id != agent_run_id,
                ),
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
        payload: GroundedResponseV1 | ResolvedClarificationV1 | TerminalOutcomeV1 | DraftReferenceV1,
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
        common = dict(
            activity_id=activity_id,
            conversation_id=claimed.conversation_id,
            conversation_resource_version=new_version,
            scenario_id=claimed.scenario_id,
            scenario_version_id=claimed.scenario_version_id,
            occurred_at=occurred_at,
        )
        if isinstance(payload, GroundedResponseV1):
            activity = AgentResponseActivityV1(
                activity_type="agent_response", response=payload, **common
            )
        elif isinstance(payload, ResolvedClarificationV1):
            activity = ClarificationActivityV1(
                activity_type="clarification", clarification=payload, **common
            )
        elif isinstance(payload, DraftReferenceV1):
            activity = DraftActivityV1(
                activity_type="draft",
                proposal_id=payload.proposal_id,
                proposal_version_id=payload.proposal_version_id,
                consequence_summary=payload.consequence_summary,
                **common,
            )
        elif isinstance(payload, TerminalOutcomeV1):
            activity = TerminalOutcomeActivityV1(
                activity_type="terminal_outcome", outcome=payload, **common
            )
        else:
            raise TypeError(f"unsupported terminal activity payload {type(payload).__name__}")
        event = PersistedEventV1(
            stream_id=claimed.conversation_id,
            sequence=sequence,
            event_type=activity.activity_type,
            occurred_at=occurred_at,
            resource_version=new_version,
            request_id=request_id,
            conversation_id=claimed.conversation_id,
            agent_run_id=claimed.agent_run_id,
            site_id=claimed.site_id,
            actor_id=claimed.actor_id,
            payload=activity,
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
                payload=_payload_to_json(activity),
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
    if isinstance(activity, DraftActivityV1):
        return {
            **common,
            "proposal_id": str(activity.proposal_id),
            "proposal_version_id": str(activity.proposal_version_id),
            "consequence_summary": activity.consequence_summary,
        }
    if isinstance(activity, ApprovalRequestActivityV1):
        return {
            **common, "approval_id": str(activity.approval_id), "approval_state": activity.approval_state,
            "agent_run_id": str(activity.agent_run_id) if activity.agent_run_id else None,
            "schedule_run_id": str(activity.schedule_run_id), "candidate_schedule_version_id": str(activity.candidate_schedule_version_id),
            "baseline_schedule_version": activity.baseline_schedule_version, "consequence_summary": activity.consequence_summary,
            "parameter_hash": activity.parameter_hash, "consequence_hash": activity.consequence_hash,
            "policy_version": activity.policy_version, "expires_at": activity.expires_at.isoformat(),
        }
    from pydantic import TypeAdapter
    if isinstance(activity, AgentResponseActivityV1):
        key, value = "response", activity.response
    elif isinstance(activity, ClarificationActivityV1):
        key, value = "clarification", activity.clarification
    else:
        key, value = "outcome", activity.outcome
    return {**common, key: TypeAdapter(type(value)).dump_python(value, mode="json")}


def _activity_from_payload(value: dict) -> ActivityItemV1:
    activity_type = value.get("activity_type")
    if activity_type not in (
        _PLANNER_MESSAGE,
        "agent_response",
        "clarification",
        "draft",
        "approval_request",
        "terminal_outcome",
    ):
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
    if activity_type == "agent_response":
        return AgentResponseActivityV1(
            **common,
            response=TypeAdapter(GroundedResponseV1).validate_python(value["response"]),
        )
    if activity_type == "clarification":
        return ClarificationActivityV1(
            **common,
            clarification=TypeAdapter(ResolvedClarificationV1).validate_python(
                value["clarification"]
            ),
        )
    if activity_type == "draft":
        return DraftActivityV1(
            **common,
            proposal_id=UUID(value["proposal_id"]),
            proposal_version_id=UUID(value["proposal_version_id"]),
            consequence_summary=value["consequence_summary"],
        )
    if activity_type == "approval_request":
        return ApprovalRequestActivityV1(
            **common, approval_id=UUID(value["approval_id"]), approval_state=value["approval_state"],
            agent_run_id=UUID(value["agent_run_id"]) if value["agent_run_id"] else None,
            schedule_run_id=UUID(value["schedule_run_id"]), candidate_schedule_version_id=UUID(value["candidate_schedule_version_id"]),
            baseline_schedule_version=value["baseline_schedule_version"], consequence_summary=value["consequence_summary"],
            parameter_hash=value["parameter_hash"], consequence_hash=value["consequence_hash"], policy_version=value["policy_version"],
            expires_at=datetime.fromisoformat(value["expires_at"]).astimezone(timezone.utc),
        )
    return TerminalOutcomeActivityV1(
        **common,
        outcome=TypeAdapter(TerminalOutcomeV1).validate_python(value["outcome"]),
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
        schedule_run_id=row.schedule_run_id,
        site_id=row.site_id,
        actor_id=row.actor_id,
        payload=_activity_from_payload(row.payload),
    )
