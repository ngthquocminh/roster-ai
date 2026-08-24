from __future__ import annotations

from application.contracts.run_snapshot import RunSnapshotV1
from tests.fixtures.repair_correctness import (
    BASELINE_ASSIGNMENTS,
    DEMAND,
    LOCKS,
    REPAIR_CONSTRAINTS,
    RepairProjectionReader,
    hard_constraint_failure_scheduler,
    infeasible_scheduler,
)


def test_seeded_repair_fixture_is_non_vacuous() -> None:
    reader = RepairProjectionReader()

    assert len(BASELINE_ASSIGNMENTS) == 1
    assert len(DEMAND) == 1
    assert DEMAND[0].family == "outbound"
    assert DEMAND[0].unit == "volume"
    assert len(LOCKS) == 1
    assert LOCKS[0].target_type == "worker_shift"
    assert REPAIR_CONSTRAINTS[0].kind == "set_min_workers_per_task"
    assert REPAIR_CONSTRAINTS[0].n == 2
    assert reader.fixture_payload["Outbound Workload"][0]["Volume"] == 800


def test_infeasible_scheduler_substitutes_only_the_solver_boundary() -> None:
    outcome = infeasible_scheduler().solve(RunSnapshotV1.__new__(RunSnapshotV1))

    assert outcome.solver_status == "INFEASIBLE"
    # The finalizer owns the stable AD-7 reason mapping.
    assert outcome.reason is None
    assert outcome.assignments == ()


def test_failed_scheduler_returns_a_feasible_but_invalid_candidate() -> None:
    outcome = hard_constraint_failure_scheduler().solve(
        RunSnapshotV1.__new__(RunSnapshotV1)
    )

    assert outcome.solver_status == "OPTIMAL"
    assert outcome.validation_facts is not None
    assert outcome.assignments == ()
