from __future__ import annotations

from dataclasses import FrozenInstanceError, fields
from datetime import datetime, timezone
from typing import get_args
from uuid import uuid4

import pytest

from application.contracts.run_snapshot import (
    GovernedSolverConfigV1,
    RunSnapshotV1,
)
from application.contracts.schedule_version import (
    ConstraintResultV1,
    MetricSetV1,
    ScheduleRunStatusV1,
    ScheduleVersionV1,
    SolverOutcomeV1,
)
from application.contracts.scenario_projection import AssignmentV1, QualificationRefV1


def test_assignment_v1_adds_defaulted_solver_provenance_fields() -> None:
    assignment = AssignmentV1("a1", "w1", "t1", "s1", 0, 60)

    assert [field.name for field in fields(assignment)] == [
        "record_id",
        "worker_id",
        "task_id",
        "shift_id",
        "start_minute",
        "end_minute",
        "qualification_refs",
        "source",
        "lock_ref",
    ]
    assert assignment.qualification_refs == ()
    assert assignment.source == "baseline"
    assert assignment.lock_ref is None

    solver_assignment = AssignmentV1(
        "a2",
        "w2",
        "t2",
        "s2",
        60,
        120,
        qualification_refs=(QualificationRefV1(task_id="t2", rate=4.0),),
        source="solver",
    )
    assert solver_assignment.qualification_refs[0].rate == 4.0


def test_schedule_run_status_is_the_exact_ad7_closed_vocabulary() -> None:
    assert get_args(ScheduleRunStatusV1) == (
        "solver_queued",
        "solver_running",
        "cancellation_requested",
        "solver_completed",
        "solver_infeasible",
        "solver_timed_out",
        "solver_cancelled",
        "solver_failed",
    )


def test_run_snapshot_requires_every_non_nullable_ad20_field() -> None:
    with pytest.raises(ValueError, match="snapshot_id"):
        RunSnapshotV1()


def test_run_snapshot_hash_is_stable_for_sorted_component_versions() -> None:
    accepted_at = datetime(2026, 8, 19, tzinfo=timezone.utc)
    values = dict(
        snapshot_id=uuid4(),
        schedule_run_id=uuid4(),
        scenario_id=uuid4(),
        scenario_version_id=uuid4(),
        checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1",
        checksum_digest="a" * 64,
        proposal_id=uuid4(),
        proposal_version_id=uuid4(),
        proposal_resource_version=1,
        solver_config=GovernedSolverConfigV1(
            engine_name="cpsat",
            seed=42,
            num_search_workers=1,
            max_deterministic_time=30.0,
            wall_time_limit_seconds=30.0,
        ),
        component_versions=(("ortools", "9.11.4210"), ("application", "1"), ("contract", "1")),
        accepted_at=accepted_at,
    )
    snapshot = RunSnapshotV1(**values)
    reordered = RunSnapshotV1(
        **{**values, "component_versions": tuple(reversed(values["component_versions"]))}
    )

    assert snapshot.component_versions == tuple(sorted(values["component_versions"]))
    assert snapshot.canonical_hash == reordered.canonical_hash
    assert snapshot.canonical_hash_algorithm == "sha256"
    assert snapshot.canonical_hash_schema_version == "rfc8785-v1"
    with pytest.raises(FrozenInstanceError):
        snapshot.checksum_digest = "b" * 64  # type: ignore[misc]


def test_schedule_contracts_are_frozen_and_transport_free() -> None:
    assert [field.name for field in fields(MetricSetV1)][-1] == "schema_version"
    assert [field.name for field in fields(ConstraintResultV1)][-1] == "schema_version"
    assert [field.name for field in fields(SolverOutcomeV1)][-1] == "schema_version"
    assert [field.name for field in fields(ScheduleVersionV1)][-1] == "schema_version"

    for contract in (RunSnapshotV1, ScheduleVersionV1):
        module_names = set(vars(__import__(contract.__module__, fromlist=["*"])))
        assert not {"fastapi", "pydantic", "sqlalchemy", "ortools"}.intersection(module_names)
