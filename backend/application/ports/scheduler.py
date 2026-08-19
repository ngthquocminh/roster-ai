"""Framework- and solver-free governed scheduling ports."""
from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID

from application.contracts.run_snapshot import RunSnapshotV1
from application.contracts.schedule_version import SolverOutcomeV1


class SolverInputSource(Protocol):
    def load(self, scenario_version_id: UUID, expected_digest: str) -> Any: ...


class SchedulerPort(Protocol):
    def solve(self, snapshot: RunSnapshotV1) -> SolverOutcomeV1: ...


__all__ = ["SchedulerPort", "SolverInputSource"]
