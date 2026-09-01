"""Append-only audit writer; it has no update or delete operation."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import Connection, insert, select
from pydantic import TypeAdapter

from adapters.postgres.schema import audit_event
from application.contracts.audit_envelope import AuditEnvelopeV1, WorkerFactsV1
from application.contracts.evidence_ref import EvidenceRefV1


def _envelope(row) -> AuditEnvelopeV1:
    return AuditEnvelopeV1(
        audit_id=row.id, attempt_id=row.attempt_id, request_id=row.request_id,
        site_id=row.site_id, initiated_by_actor_id=row.initiated_by_actor_id,
        decided_by_actor_id=row.decided_by_actor_id, conversation_id=row.conversation_id,
        agent_run_id=row.agent_run_id, approval_id=row.approval_id,
        schedule_run_id=row.schedule_run_id, action=row.action, outcome=row.outcome,
        success=row.success, effect_key=row.effect_key, before_version=row.before_version,
        after_version=row.after_version, safe_summary=row.safe_summary,
        parameter_hash=row.parameter_hash, consequence_hash=row.consequence_hash,
        policy_version=row.policy_version, app_version=row.app_version,
        worker_facts=TypeAdapter(WorkerFactsV1).validate_python(row.worker_facts),
        evidence_refs=TypeAdapter(tuple[EvidenceRefV1, ...]).validate_python(row.evidence_refs),
        occurred_at=row.occurred_at,
    )


class PostgresAuditWriter:
    def append(self, connection: Connection, envelope: AuditEnvelopeV1) -> None:
        connection.execute(insert(audit_event).values(
            id=envelope.audit_id, site_id=envelope.site_id, attempt_id=envelope.attempt_id, request_id=envelope.request_id,
            initiated_by_actor_id=envelope.initiated_by_actor_id, decided_by_actor_id=envelope.decided_by_actor_id,
            conversation_id=envelope.conversation_id, agent_run_id=envelope.agent_run_id, approval_id=envelope.approval_id,
            schedule_run_id=envelope.schedule_run_id, action=envelope.action, outcome=envelope.outcome, success=envelope.success,
            effect_key=envelope.effect_key, before_version=envelope.before_version, after_version=envelope.after_version,
            safe_summary=envelope.safe_summary, parameter_hash=envelope.parameter_hash, consequence_hash=envelope.consequence_hash,
            policy_version=envelope.policy_version, app_version=envelope.app_version,
            worker_facts=TypeAdapter(dict).dump_python(asdict(envelope.worker_facts), mode="json"),
            evidence_refs=TypeAdapter(tuple).dump_python(envelope.evidence_refs, mode="json"), occurred_at=envelope.occurred_at,
        ))


class PostgresAuditReader:
    def list_for_schedule_run(self, connection: Connection, *, schedule_run_id, site_id):
        statement = (
            select(audit_event)
            .where(
                audit_event.c.schedule_run_id == schedule_run_id,
                audit_event.c.site_id == site_id,
            )
            .order_by(audit_event.c.occurred_at, audit_event.c.id)
        )
        return tuple(_envelope(row) for row in connection.execute(statement).all())
