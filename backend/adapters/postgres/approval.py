"""PostgreSQL approval repository; it deliberately never commits."""
from __future__ import annotations

from sqlalchemy import Connection, insert, select

from adapters.postgres.schema import approval_request
from application.contracts.approval_binding import ApprovalBindingV1


def _binding(row) -> ApprovalBindingV1:
    return ApprovalBindingV1(
        approval_id=row.id, state=row.state, site_id=row.site_id, action=row.action,
        initiated_by_actor_id=row.initiated_by_actor_id, decided_by_actor_id=row.decided_by_actor_id,
        conversation_id=row.conversation_id, agent_run_id=row.agent_run_id, schedule_run_id=row.schedule_run_id,
        candidate_schedule_version_id=row.candidate_schedule_version_id, scenario_version_id=row.scenario_version_id,
        baseline_schedule_version=row.baseline_schedule_version,
        baseline_resource_version=row.baseline_resource_version, parameter_hash=row.parameter_hash,
        consequence_summary=row.consequence_summary, consequence_hash=row.consequence_hash,
        checksum_algorithm=row.checksum_algorithm, checksum_schema_version=row.checksum_schema_version,
        policy_version=row.policy_version, created_at=row.created_at, expires_at=row.expires_at,
        decided_at=row.decided_at, consumed_at=row.consumed_at, request_effect_key=row.request_effect_key,
        resource_version=row.resource_version,
    )


class PostgresApprovalRepository:
    """Every read carries an explicit `site_id` predicate.

    RLS already forces site isolation on `approval_request`, and that stays the
    real boundary. But every sibling repository here (`get_run`, `get_candidate`,
    `PostgresSiteBaselineReader.get`) also filters explicitly, so isolation never
    rests on a single mechanism -- a caller that opens a connection without
    `site_context` still cannot read another site's binding.
    """

    def create_pending(self, connection: Connection, *, binding: ApprovalBindingV1, pending_payload: dict | None) -> None:
        connection.execute(insert(approval_request).values(
            id=binding.approval_id, site_id=binding.site_id, state=binding.state, action=binding.action,
            initiated_by_actor_id=binding.initiated_by_actor_id, decided_by_actor_id=binding.decided_by_actor_id,
            conversation_id=binding.conversation_id, agent_run_id=binding.agent_run_id, schedule_run_id=binding.schedule_run_id,
            candidate_schedule_version_id=binding.candidate_schedule_version_id, scenario_version_id=binding.scenario_version_id,
            baseline_schedule_version=binding.baseline_schedule_version,
            baseline_resource_version=binding.baseline_resource_version, parameter_hash=binding.parameter_hash,
            consequence_summary=binding.consequence_summary, consequence_hash=binding.consequence_hash,
            checksum_algorithm=binding.checksum_algorithm, checksum_schema_version=binding.checksum_schema_version,
            policy_version=binding.policy_version, created_at=binding.created_at, expires_at=binding.expires_at,
            request_effect_key=binding.request_effect_key, resource_version=binding.resource_version, pending_payload=pending_payload,
        ))

    def get(self, connection: Connection, *, approval_id, site_id):
        row = connection.execute(select(approval_request).where(approval_request.c.id == approval_id, approval_request.c.site_id == site_id)).one_or_none()
        return _binding(row) if row else None

    def list_for_schedule_run(self, connection: Connection, *, schedule_run_id, site_id):
        return tuple(_binding(row) for row in connection.execute(select(approval_request).where(approval_request.c.schedule_run_id == schedule_run_id, approval_request.c.site_id == site_id).order_by(approval_request.c.created_at)).all())

    def get_pending_for_agent_run(self, connection: Connection, *, agent_run_id, site_id):
        row = connection.execute(select(approval_request).where(approval_request.c.agent_run_id == agent_run_id, approval_request.c.site_id == site_id, approval_request.c.state == "pending")).one_or_none()
        return _binding(row) if row else None
