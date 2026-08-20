"""Immutable governed solver-input contracts (AD-9, AD-20)."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from application.contracts.canonical import contract_digest
from application.contracts.evidence_ref import EvidenceRefV1
from application.contracts.proposal import DraftConstraintV1
from application.contracts.scenario_projection import ConstraintV1, LockV1

SCHEMA_VERSION = "1"


def _json_value(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


@dataclass(frozen=True)
class GovernedSolverConfigV1:
    """Application-owned reproducible CP-SAT ceilings."""

    engine_name: str = "cpsat"
    seed: int = 42
    num_search_workers: int = 1
    max_deterministic_time: float = 30.0
    wall_time_limit_seconds: float = 30.0
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        positive = {
            "seed": self.seed,
            "num_search_workers": self.num_search_workers,
            "max_deterministic_time": self.max_deterministic_time,
            "wall_time_limit_seconds": self.wall_time_limit_seconds,
        }
        if not self.engine_name:
            raise ValueError("engine_name is required")
        for name, value in positive.items():
            if value <= 0:
                raise ValueError(f"{name} must be positive")


@dataclass(frozen=True)
class RunSnapshotV1:
    """Accepted input manifest; identity plus checksums, never fixture payload."""

    snapshot_id: UUID | None = None
    schedule_run_id: UUID | None = None
    scenario_id: UUID | None = None
    scenario_version_id: UUID | None = None
    checksum_algorithm: str = ""
    checksum_schema_version: str = ""
    checksum_digest: str = ""
    baseline_schedule_version: str | None = None
    proposal_id: UUID | None = None
    proposal_version_id: UUID | None = None
    proposal_resource_version: int = 0
    preserved_locks: tuple[LockV1, ...] = ()
    constraints: tuple[DraftConstraintV1, ...] = ()
    objectives: tuple[ConstraintV1, ...] = ()
    solver_config: GovernedSolverConfigV1 | None = None
    component_versions: tuple[tuple[str, str], ...] = ()
    accepted_at: datetime | None = None
    input_evidence_refs: tuple[EvidenceRefV1, ...] = ()
    canonical_hash: str = ""
    canonical_hash_algorithm: str = "sha256"
    canonical_hash_schema_version: str = "rfc8785-v1"
    schema_version: str = SCHEMA_VERSION

    def __post_init__(self) -> None:
        required = (
            "snapshot_id",
            "schedule_run_id",
            "scenario_id",
            "scenario_version_id",
            "checksum_algorithm",
            "checksum_schema_version",
            "checksum_digest",
            "proposal_id",
            "proposal_version_id",
            "proposal_resource_version",
            "solver_config",
            "component_versions",
            "accepted_at",
        )
        for name in required:
            value = getattr(self, name)
            if value is None or value == "" or value == () or value == 0:
                raise ValueError(f"{name} is required")
        assert self.accepted_at is not None
        if self.accepted_at.tzinfo is None or self.accepted_at.utcoffset() != timezone.utc.utcoffset(self.accepted_at):
            raise ValueError("accepted_at must be UTC-aware")

        sorted_versions = tuple(sorted(self.component_versions))
        object.__setattr__(self, "component_versions", sorted_versions)
        algorithm, digest_schema, digest = contract_digest(self.canonical_payload())
        if self.canonical_hash and self.canonical_hash != digest:
            raise ValueError("canonical_hash does not match the snapshot payload")
        object.__setattr__(self, "canonical_hash", digest)
        object.__setattr__(self, "canonical_hash_algorithm", algorithm)
        object.__setattr__(self, "canonical_hash_schema_version", digest_schema)

    def canonical_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        for field_name in (
            "canonical_hash",
            "canonical_hash_algorithm",
            "canonical_hash_schema_version",
        ):
            payload.pop(field_name)
        return _json_value(payload)


__all__ = ["SCHEMA_VERSION", "GovernedSolverConfigV1", "RunSnapshotV1"]
