from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

from adapters.postgres.solver_input import (
    PostgresSolverInputSource,
    SnapshotDigestMismatchError,
    SnapshotInputMissingError,
)
from application.contracts.canonical import contract_digest
from application.contracts.proposal import DraftConstraintV1, ResolvedEntityV1
from application.contracts.run_snapshot import GovernedSolverConfigV1, RunSnapshotV1
from engine.governed_adapter import (
    GovernedSchedulerAdapter,
    _constraints_to_overrides,
    _hours_to_minutes,
    _minutes_to_hours,
    _wire_employment_caps,
)


class _Result:
    def __init__(self, row) -> None:
        self.row = row

    def one_or_none(self):
        return self.row


class _Connection:
    def __init__(self, row) -> None:
        self.row = row

    def execute(self, _statement):
        return _Result(self.row)


class _PayloadSource:
    def __init__(self, payload) -> None:
        self.payload = payload

    def load(self, _scenario_version_id, _expected_digest):
        return self.payload


def _entity(group, record_id):
    return ResolvedEntityV1(group=group, record_id=record_id, label=record_id)


def test_solver_input_source_recomputes_the_raw_payload_digest() -> None:
    payload = {"Scenario Range": [{"PeriodStartDate": "2026-01-01", "PeriodEndDate": "2026-01-02"}]}
    digest = contract_digest(payload)[2]
    row = SimpleNamespace(payload=payload, checksum_digest=digest)

    assert PostgresSolverInputSource(_Connection(row)).load(uuid4(), digest) == payload

    with pytest.raises(SnapshotDigestMismatchError):
        PostgresSolverInputSource(_Connection(row)).load(uuid4(), "f" * 64)
    with pytest.raises(SnapshotInputMissingError):
        PostgresSolverInputSource(_Connection(None)).load(uuid4(), digest)


@pytest.mark.parametrize("minute", (0, 1, 60, 1204, 10080))
def test_minute_hour_conversion_round_trips_at_fixture_precision(minute) -> None:
    assert _hours_to_minutes(_minutes_to_hours(minute)) == minute


def test_all_five_constraints_translate_to_existing_override_vocabulary() -> None:
    task = _entity("work-areas-and-tasks", "task-1")
    worker = _entity("workers", "worker-1")
    constraints = (
        DraftConstraintV1(kind="set_min_workers_per_task", resolved_entities=(task,), n=2),
        DraftConstraintV1(kind="scale_demand", resolved_entities=(task,), factor=1.5),
        DraftConstraintV1(kind="lock_worker_shift", resolved_entities=(worker,), start_minute=1500, end_minute=1980),
        DraftConstraintV1(kind="exclude_worker_from_task", resolved_entities=(worker, task)),
        DraftConstraintV1(kind="set_max_hours", resolved_entities=(worker,), max_hours=24.0),
    )

    overrides = _constraints_to_overrides(constraints)

    assert [override.tool for override in overrides] == [constraint.kind for constraint in constraints]
    assert overrides[0].args == {"task_id": "task-1", "n": 2}
    assert overrides[1].args == {"task_id": "task-1", "factor": 1.5}
    assert overrides[2].args == {"member_id": "worker-1", "day": 1}
    assert overrides[3].args == {"member_id": "worker-1", "task_id": "task-1"}
    assert overrides[4].args == {"member_id": "worker-1", "max_hours": 24.0}
    assert all(override.id.startswith("ov_") for override in overrides)


def test_employment_caps_come_from_shift_constraint_rows() -> None:
    problem = SimpleNamespace(max_hours_per_week={})
    payload = {
        "Shift Constraint": [
            {"ConstraintType": "Maximum Hours a Week", "ValueType": "Casual", "Value": "40"},
            {"ConstraintType": "MinimumHoursBetweenShifts", "ValueType": "Casual", "Value": "10"},
        ]
    }

    _wire_employment_caps(problem, payload)

    assert problem.max_hours_per_week == {"Casual": 40.0}


def test_reproducible_configuration_is_identical_across_three_real_solves() -> None:
    payload = json.loads(
        (Path(__file__).resolve().parents[2] / "data" / "sample_tiny_input.json")
        .read_text(encoding="utf-8")
    )
    digest = contract_digest(payload)[2]
    snapshot = RunSnapshotV1(
        snapshot_id=uuid4(), schedule_run_id=uuid4(), scenario_id=uuid4(),
        scenario_version_id=uuid4(), checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1", checksum_digest=digest,
        proposal_id=uuid4(), proposal_version_id=uuid4(), proposal_resource_version=1,
        solver_config=GovernedSolverConfigV1(
            engine_name="cpsat", seed=42, num_search_workers=1,
            max_deterministic_time=1.0, wall_time_limit_seconds=30.0,
        ),
        component_versions=(("application", "1"), ("contract", "1"), ("ortools", "9.11.4210")),
        accepted_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )
    deterministic = [
        GovernedSchedulerAdapter(_PayloadSource(payload)).solve(snapshot)
        for _ in range(3)
    ]
    multi_snapshot = replace(
        snapshot,
        canonical_hash="",
        solver_config=replace(
            snapshot.solver_config,
            num_search_workers=8,
            wall_time_limit_seconds=3.0,
        ),
    )
    multi = [
        GovernedSchedulerAdapter(
            _PayloadSource(payload), use_deterministic_time=False
        ).solve(multi_snapshot)
        for _ in range(3)
    ]

    assignment_keys = [
        tuple((a.worker_id, a.task_id, a.start_minute, a.end_minute) for a in result.assignments)
        for result in deterministic
    ]
    assert assignment_keys[0] == assignment_keys[1] == assignment_keys[2]
    assert len({result.solver_status for result in deterministic}) == 1
    print("deterministic_measurements", [
        (r.round1_value, r.round2_value, r.wall_time_seconds, r.solver_status,
         len(r.assignments), len({a.worker_id for a in r.assignments}))
        for r in deterministic
    ])
    print("multi_worker_measurements", [
        (r.round1_value, r.round2_value, r.wall_time_seconds, r.solver_status,
         len(r.assignments), len({a.worker_id for a in r.assignments}))
        for r in multi
    ])


def test_one_wall_ceiling_bounds_both_solver_rounds() -> None:
    payload = json.loads(
        (Path(__file__).resolve().parents[2] / "data" / "sample_tiny_input.json")
        .read_text(encoding="utf-8")
    )
    snapshot = RunSnapshotV1(
        snapshot_id=uuid4(), schedule_run_id=uuid4(), scenario_id=uuid4(),
        scenario_version_id=uuid4(), checksum_algorithm="sha256",
        checksum_schema_version="rfc8785-v1", checksum_digest=contract_digest(payload)[2],
        proposal_id=uuid4(), proposal_version_id=uuid4(), proposal_resource_version=1,
        solver_config=GovernedSolverConfigV1(
            engine_name="cpsat", seed=42, num_search_workers=1,
            max_deterministic_time=100.0, wall_time_limit_seconds=0.25,
        ),
        component_versions=(("application", "1"), ("contract", "1"), ("ortools", "9.11.4210")),
        accepted_at=datetime(2026, 8, 19, tzinfo=timezone.utc),
    )

    outcome = GovernedSchedulerAdapter(_PayloadSource(payload)).solve(snapshot)

    assert outcome.solver_status == "UNKNOWN"
    assert outcome.wall_time_seconds <= 0.40
