"""Application port for immutable snapshots and schedule-run persistence."""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from application.contracts.run_snapshot import RunSnapshotV1


class ScheduleRunRepository(Protocol):
    def create_queued_run(
        self,
        connection: Any,
        *,
        snapshot: RunSnapshotV1,
        site_id: UUID,
    ) -> None: ...


__all__ = ["ScheduleRunRepository"]
