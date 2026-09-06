"""Read and re-verify raw immutable solver input at the PostgreSQL edge."""
from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import Connection, select

from adapters.postgres.schema import scenario_version
from application.contracts.canonical import contract_digest


class SolverInputError(ValueError):
    """Raised when the frozen solver input cannot be read or re-verified.

    Deliberately NOT a fatal-job error. `execute_schedule_run` catches it with
    every other solver failure and finalizes the run as
    `("solver_failed", <this class's `code`>)`, so the specific cause —
    `snapshot_input_missing` or `snapshot_digest_mismatch` — reaches the Runs
    list and the provenance timeline. Routing it through the lease boundary's
    fatal path instead would replace that with a generic
    `job_execution_failed` and make both `code` attributes dead.
    """

    code = "solver_input_error"


class SnapshotInputMissingError(SolverInputError):
    code = "snapshot_input_missing"


class SnapshotDigestMismatchError(SolverInputError):
    code = "snapshot_digest_mismatch"


class PostgresSolverInputSource:
    def __init__(self, connection: Connection):
        self._connection = connection

    def load(self, scenario_version_id: UUID, expected_digest: str) -> Any:
        row = self._connection.execute(
            select(
                scenario_version.c.payload,
                scenario_version.c.checksum_digest,
            ).where(scenario_version.c.id == scenario_version_id)
        ).one_or_none()
        if row is None:
            raise SnapshotInputMissingError(
                f"scenario version {scenario_version_id} is not readable"
            )
        recomputed = contract_digest(row.payload)[2]
        if row.checksum_digest != expected_digest or recomputed != expected_digest:
            raise SnapshotDigestMismatchError(
                "raw solver input no longer matches the frozen snapshot digest"
            )
        return row.payload


__all__ = [
    "PostgresSolverInputSource",
    "SnapshotDigestMismatchError",
    "SnapshotInputMissingError",
    "SolverInputError",
]
