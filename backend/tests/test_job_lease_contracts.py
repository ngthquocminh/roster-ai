from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from typing import get_args
from uuid import uuid4

import pytest

from application.contracts.job_lease import JobLeaseV1, JobStatusV1, JobTypeV1


def test_job_lease_uses_closed_workflow_vocabularies() -> None:
    assert get_args(JobTypeV1) == ("schedule_run_execute",)
    assert get_args(JobStatusV1) == ("queued", "leased", "completed", "failed")


def test_job_lease_contains_the_ad20_lease_and_fencing_shape() -> None:
    assert [field.name for field in fields(JobLeaseV1)] == [
        "job_id",
        "job_type",
        "status",
        "site_id",
        "actor_id",
        "attempt_id",
        "contract_version",
        "capability_version",
        "schedule_run_id",
        "idempotency_key",
        "lease_owner",
        "lease_expires_at",
        "heartbeat_at",
        "fencing_epoch",
        "cancellation_requested",
        "created_at",
    ]


def test_job_lease_requires_enqueue_time_fields_but_not_lease_time_fields() -> None:
    with pytest.raises(ValueError, match="job_id"):
        JobLeaseV1()

    job = JobLeaseV1(
        job_id=uuid4(),
        job_type="schedule_run_execute",
        status="queued",
        site_id=uuid4(),
        actor_id=uuid4(),
        contract_version="1",
        schedule_run_id=uuid4(),
        idempotency_key="enqueue-1",
        created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    assert job.attempt_id is None
    assert job.lease_owner is None
    assert job.fencing_epoch == 0
    with pytest.raises(FrozenInstanceError):
        job.fencing_epoch = 1  # type: ignore[misc]


def test_job_lease_rejects_incomplete_or_naive_lease_state() -> None:
    required = dict(
        job_id=uuid4(),
        job_type="schedule_run_execute",
        status="leased",
        site_id=uuid4(),
        actor_id=uuid4(),
        contract_version="1",
        schedule_run_id=uuid4(),
        idempotency_key="enqueue-1",
        created_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
    )
    with pytest.raises(ValueError, match="attempt_id"):
        JobLeaseV1(**required)
    with pytest.raises(ValueError, match="UTC-aware"):
        JobLeaseV1(
            **required,
            attempt_id=uuid4(),
            lease_owner="worker-1",
            lease_expires_at=datetime(2026, 8, 20),
            heartbeat_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
            fencing_epoch=1,
        )
