"""Durable workflow job lease and fencing contract (AD-6, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID


JobTypeV1 = Literal["schedule_run_execute"]
JobStatusV1 = Literal["queued", "leased", "completed"]

JOB_TYPES: frozenset[str] = frozenset(("schedule_run_execute",))
JOB_STATUSES: frozenset[str] = frozenset(("queued", "leased", "completed"))

#: `command_idempotency.idempotency_key` is `String(40)` and the enqueue bundle
#: writes both tables in one transaction, so a longer key would pass the job
#: insert and then abort the whole transaction on the second one with a raw
#: `StringDataRightTruncation`. The narrower column is the real bound; validate
#: against it here rather than letting the driver report it.
MAX_IDEMPOTENCY_KEY_LENGTH = 40


@dataclass(frozen=True)
class LeaseRenewalV1:
    """Outcome of one heartbeat against a job the caller believes it holds.

    Decision 7 requires both lease functions to *read* `cancellation_requested`
    so a leased-but-cancelled job can reach the worker without Story 3.4 having
    to invent new plumbing. A bare boolean could not carry it.
    """

    renewed: bool
    cancellation_requested: bool = False


@dataclass(frozen=True)
class JobLeaseV1:
    """One durable compute job and its current lease acquisition, if any."""

    job_id: UUID | None = None
    job_type: JobTypeV1 | None = None
    status: JobStatusV1 = "queued"
    site_id: UUID | None = None
    actor_id: UUID | None = None
    attempt_id: UUID | None = None
    contract_version: str = ""
    capability_version: str | None = None
    schedule_run_id: UUID | None = None
    idempotency_key: str = ""
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    fencing_epoch: int = 0
    cancellation_requested: bool = False
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        for name in (
            "job_id",
            "site_id",
            "job_type",
            "schedule_run_id",
            "actor_id",
            "contract_version",
            "idempotency_key",
        ):
            value = getattr(self, name)
            if value is None or value == "":
                raise ValueError(f"{name} is required")
        if len(self.idempotency_key) > MAX_IDEMPOTENCY_KEY_LENGTH:
            raise ValueError(
                f"idempotency_key must be at most {MAX_IDEMPOTENCY_KEY_LENGTH} characters"
            )
        if self.job_type not in JOB_TYPES:
            raise ValueError(f"unknown job_type {self.job_type!r}")
        if self.status not in JOB_STATUSES:
            raise ValueError(f"unknown status {self.status!r}")
        if self.fencing_epoch < 0:
            raise ValueError("fencing_epoch must not be negative")
        if self.status == "queued":
            for name in ("attempt_id", "lease_owner", "lease_expires_at"):
                if getattr(self, name) is not None:
                    raise ValueError(f"{name} must be unset on a queued job")
        if self.status == "leased":
            for name in (
                "attempt_id",
                "lease_owner",
                "lease_expires_at",
                "heartbeat_at",
            ):
                if getattr(self, name) is None:
                    raise ValueError(f"{name} is required for a leased job")
            if self.fencing_epoch <= 0:
                raise ValueError("fencing_epoch must be positive for a leased job")
        for value in (self.lease_expires_at, self.heartbeat_at, self.created_at):
            if value is not None and (
                value.tzinfo is None
                or value.utcoffset() != timezone.utc.utcoffset(value)
            ):
                raise ValueError("job timestamps must be UTC-aware")


__all__ = [
    "JOB_STATUSES",
    "JOB_TYPES",
    "MAX_IDEMPOTENCY_KEY_LENGTH",
    "JobLeaseV1",
    "JobStatusV1",
    "JobTypeV1",
    "LeaseRenewalV1",
]
