"""SQL-free ports for governance-owned approval and evidence-owned audit rows."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from application.contracts.approval_binding import ApprovalBindingV1
from application.contracts.audit_envelope import AuditEnvelopeV1


class ApprovalRepository(Protocol):
    def create_pending(self, connection: Any, *, binding: ApprovalBindingV1, pending_payload: dict | None) -> None: ...
    def get(self, connection: Any, *, approval_id: UUID, site_id: UUID) -> ApprovalBindingV1 | None: ...
    def list_for_schedule_run(self, connection: Any, *, schedule_run_id: UUID, site_id: UUID) -> tuple[ApprovalBindingV1, ...]: ...
    def get_pending_for_agent_run(self, connection: Any, *, agent_run_id: UUID, site_id: UUID) -> ApprovalBindingV1 | None: ...
    def terminalize(self, connection: Any, *, approval_id: UUID, site_id: UUID, state: str, decided_by_actor_id: UUID, decided_at: datetime, expected_resource_version: int) -> ApprovalBindingV1 | None: ...


class AuditWriter(Protocol):
    def append(self, connection: Any, envelope: AuditEnvelopeV1) -> None: ...
