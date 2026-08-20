"""Durable workflow job lease and fencing contract (AD-6, AD-20)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID


JobTypeV1 = Literal["schedule_run_execute"]
JobStatusV1 = Literal["queued", "leased", "completed"]


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
        ):
            value = getattr(self, name)
            if value is None or value == "":
                raise ValueError(f"{name} is required")
        if self.fencing_epoch < 0:
            raise ValueError("fencing_epoch must not be negative")
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


__all__ = ["JobLeaseV1", "JobStatusV1", "JobTypeV1"]
