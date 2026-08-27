"""Append-only audit writer; it has no update or delete operation."""
from __future__ import annotations

from dataclasses import asdict

from sqlalchemy import Connection, insert
from pydantic import TypeAdapter

from adapters.postgres.schema import audit_event
from application.contracts.audit_envelope import AuditEnvelopeV1


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
