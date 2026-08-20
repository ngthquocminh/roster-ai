"""Application port for immutable snapshots and schedule-run persistence."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import ScheduleRunStatusV1, ScheduleVersionV1


class ScheduleRunRepository(Protocol):
    def mark_running(
        self, connection: Any, *, run_id: UUID, site_id: UUID
    ) -> None: ...

    def create_queued_run(
        self,
        connection: Any,
        *,
        snapshot: RunSnapshotV1,
        site_id: UUID,
    ) -> None: ...

    def finalize_run(
        self,
        connection: Any,
        *,
        run_id: UUID,
        site_id: UUID,
        status: ScheduleRunStatusV1,
        reason: str | None,
        candidate: ScheduleVersionV1 | None,
        finished_at: datetime | None = None,
    ) -> None: ...


__all__ = ["ScheduleRunRepository"]
