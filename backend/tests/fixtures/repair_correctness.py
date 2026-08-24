"""Synthetic Wednesday repair fixture for Story 3.10's proof suite.

The raw payload is consumed by the real governed CP-SAT adapter.  The
projection reader exposes the same facts plus a deliberately incomplete
baseline and a non-empty lock, supplies that production cannot represent yet.
"""
from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID

from application.contracts.canonical import contract_digest
from application.contracts.evidence_ref import TaskResolutionV1
from application.contracts.proposal import DraftConstraintV1, ResolvedEntityV1
from application.contracts.schedule_version import SolverOutcomeV1, ValidationFactsV1
from application.contracts.scenario_projection import (
    AssignmentV1,
    AvailabilityWindowV1,
    DemandIntervalV1,
    LockV1,
    QualificationRefV1,
    ScenarioOverviewV1,
    TaskV1,
    WorkerV1,
)
from application.ports.scenario_projection import (
    AssignmentPageV1,
    ConstraintPageV1,
    DemandIntervalPageV1,
    GroupQueryKeysV1,
    LockPageV1,
    TaskPageV1,
    WorkerPageV1,
)


SCENARIO_ID = UUID("31000000-0000-0000-0000-000000000001")
SCENARIO_VERSION_ID = UUID("31000000-0000-0000-0000-000000000002")
SITE_ID = UUID("31000000-0000-0000-0000-000000000003")
TASK_ID = "pick-wednesday"
LOCKED_WORKER_ID = "lock01"
REPAIR_WORKER_ID = "repair02"
LOCKED_SHIFT_ID = "shift_lock01_ros0_tpl001_80"
FIXTURE_PAYLOAD = {
    "Scenario Range": [
        {
            "PeriodStartDate": "2026-08-12T00:00:00",
            "PeriodEndDate": "2026-08-13T00:00:00",
        }
    ],
    "Function": [{"FunctionID": "fn-pick", "Name": "Outbound Pick"}],
    "Task": [
        {
            "TaskID": TASK_ID,
            "Task": "Wednesday outbound pick",
            "FunctionID": "fn-pick",
            "AreaID": "outbound",
            "UnitTypeID": "cases",
        }
    ],
    "Team Member": [
        {
            "ContactID": LOCKED_WORKER_ID,
            "Team Member": "Locked Worker",
            "EmploymentType": "Full Time",
            "GradeID": "grade-1",
            "EBAID": "eba-1",
            "ContractedHours": 40,
        },
        {
            "ContactID": REPAIR_WORKER_ID,
            "Team Member": "Repair Worker",
            "EmploymentType": "Full Time",
            "GradeID": "grade-1",
            "EBAID": "eba-1",
            "ContractedHours": 40,
        },
    ],
    "EBA Grade Rate": [
        {
            "EBAID": "eba-1",
            "GradeID": "grade-1",
            "RateType": "Base Rate",
            "Amount": 40,
        }
    ],
    "Roster Profile": [
        {
            "ContactID": LOCKED_WORKER_ID,
            "StartDateTime": "2026-08-12T08:00:00",
            "EndDateTime": "2026-08-12T12:00:00",
        },
        {
            "ContactID": REPAIR_WORKER_ID,
            "StartDateTime": "2026-08-12T08:00:00",
            "EndDateTime": "2026-08-12T12:00:00",
        },
    ],
    "Team Member Qualification and Performance": [
        {
            "ContactID": LOCKED_WORKER_ID,
            "TaskID": TASK_ID,
            "DefaultTaskRate": 100,
        },
        {
            "ContactID": REPAIR_WORKER_ID,
            "TaskID": TASK_ID,
            "DefaultTaskRate": 100,
        },
    ],
    "Outbound Workload": [
        {
            "TaskID": TASK_ID,
            "StartDateTime": "2026-08-12T08:00:00",
            "EndDateTime": "2026-08-12T12:00:00",
            "Volume": 800,
        }
    ],
    "Shift Schedule Template": [
        {
            "ShiftScheduleTemplateID": "tpl001",
            "Name": "Four hours",
            "TotalShiftHours": 4,
        }
    ],
    "Shift Constraint": [
        {
            "ConstraintType": "Maximum Hours a Week",
            "ValueType": "Full Time",
            "Value": 40,
        }
    ],
}


def _digest() -> str:
    return contract_digest(FIXTURE_PAYLOAD)[2]


FIXTURE_CHECKSUM_DIGEST = _digest()
TASKS = (
    TaskV1(
        TASK_ID,
        TASK_ID,
        "Wednesday outbound pick",
        "Outbound Pick",
        "outbound",
        "Outbound",
        "cases",
    ),
)
WORKERS = (
    WorkerV1(
        LOCKED_WORKER_ID,
        LOCKED_WORKER_ID,
        "Locked Worker",
        "Full Time",
        "grade-1",
        "eba-1",
        40,
        (QualificationRefV1(TASK_ID, 100),),
        (AvailabilityWindowV1("roster", 480, 720),),
    ),
    WorkerV1(
        REPAIR_WORKER_ID,
        REPAIR_WORKER_ID,
        "Repair Worker",
        "Full Time",
        "grade-1",
        "eba-1",
        40,
        (QualificationRefV1(TASK_ID, 100),),
        (AvailabilityWindowV1("roster", 480, 720),),
    ),
)
DEMAND = (
    DemandIntervalV1(
        "wed-outbound-gap", "outbound", TASK_ID, "outbound", 480, 720, 800, "volume"
    ),
)
BASELINE_ASSIGNMENTS = (
    AssignmentV1(
        "baseline-locked", LOCKED_WORKER_ID, TASK_ID, LOCKED_SHIFT_ID, 480, 720
    ),
)
LOCKS = (
    LockV1(
        "lock-wednesday-worker",
        "worker_shift",
        f"{LOCKED_WORKER_ID}:{LOCKED_SHIFT_ID}",
        "scenario",
        "seeded",
    ),
)
REPAIR_CONSTRAINTS = (
    DraftConstraintV1(
        kind="set_min_workers_per_task",
        resolved_entities=(
            ResolvedEntityV1(
                "work-areas-and-tasks",
                TASK_ID,
                "Wednesday outbound pick",
                SCENARIO_VERSION_ID,
            ),
        ),
        n=2,
        description="Keep two workers on the Wednesday outbound task",
    ),
)


class RepairProjectionReader:
    fixture_payload = FIXTURE_PAYLOAD

    def get_query_keys(self, group):
        return GroupQueryKeysV1(group=group, sort_keys=(), filter_keys=())

    def get_overview(self, _connection, scenario_id):
        if scenario_id != SCENARIO_ID:
            return None
        return ScenarioOverviewV1(
            SCENARIO_ID,
            SCENARIO_VERSION_ID,
            SITE_ID,
            "story-3.10-repair",
            "Wednesday repair correctness",
            "v1",
            "sha256",
            "rfc8785-v1",
            FIXTURE_CHECKSUM_DIGEST,
            datetime(2026, 8, 12, tzinfo=timezone.utc),
            "UTC",
            1440,
            None,
            datetime(2026, 8, 12, tzinfo=timezone.utc),
            1,
            len(TASKS),
            len(WORKERS),
            len(DEMAND),
            len(BASELINE_ASSIGNMENTS),
            len(LOCKS),
            0,
        )

    def _page(self, rows, query, page_type):
        items = rows[query.cursor : query.cursor + query.limit]
        end = query.cursor + len(items)
        return page_type(
            SCENARIO_ID,
            SCENARIO_VERSION_ID,
            SITE_ID,
            items,
            end if end < len(rows) else None,
            len(rows),
            len(rows),
        )

    def get_tasks(self, _connection, _scenario_id, query):
        return self._page(TASKS, query, TaskPageV1)

    def get_workers(self, _connection, _scenario_id, query):
        return self._page(WORKERS, query, WorkerPageV1)

    def get_demand(self, _connection, _scenario_id, query):
        return self._page(DEMAND, query, DemandIntervalPageV1)

    def get_baseline_assignments(self, _connection, _scenario_id, query):
        return self._page(BASELINE_ASSIGNMENTS, query, AssignmentPageV1)

    def get_locks(self, _connection, _scenario_id, query):
        return self._page(LOCKS, query, LockPageV1)

    def get_constraints(self, _connection, _scenario_id, query):
        return self._page((), query, ConstraintPageV1)

    def resolve_task(
        self, _connection, scenario_id, scenario_version_id, record_id
    ):
        item = (
            next((task for task in TASKS if task.record_id == record_id), None)
            if scenario_id == SCENARIO_ID
            else None
        )
        return TaskResolutionV1(
            outcome="resolved" if item is not None else "not_found",
            scenario_id=scenario_id,
            current_scenario_version_id=scenario_version_id,
            item=item,
        )


class FixturePayloadSource:
    def load(self, scenario_version_id, expected_checksum_digest):
        assert scenario_version_id == SCENARIO_VERSION_ID
        assert expected_checksum_digest == FIXTURE_CHECKSUM_DIGEST
        return FIXTURE_PAYLOAD


def infeasible_scheduler():
    return SimpleNamespace(
        solve=lambda _snapshot: SolverOutcomeV1(solver_status="INFEASIBLE")
    )


def hard_constraint_failure_scheduler():
    """Decision E option 2: a fake `SchedulerPort` returning `OPTIMAL` over
    assignments that fail validation -- specifically, empty assignments
    against the seeded worker-shift lock, tripping `preserved_lock`
    (proved in `test_failed_scheduler_trips_exactly_the_preserved_lock_check`).
    Not the corrupted-real-solve option (unqualified-worker reassignment)."""
    return SimpleNamespace(
        solve=lambda _snapshot: SolverOutcomeV1(
            solver_status="OPTIMAL",
            assignments=(),
            validation_facts=ValidationFactsV1(
                horizon_minutes=1440,
                workers=(),
                selected_shifts=(),
                max_hours_per_week=(),
                max_shifts_per_day=(),
                minimum_gap_minutes=0,
                tasks=TASKS,
                demand_intervals=DEMAND,
            ),
        )
    )


__all__ = [
    "BASELINE_ASSIGNMENTS",
    "DEMAND",
    "FIXTURE_CHECKSUM_DIGEST",
    "FIXTURE_PAYLOAD",
    "FixturePayloadSource",
    "LOCKS",
    "REPAIR_CONSTRAINTS",
    "RepairProjectionReader",
    "SCENARIO_ID",
    "SCENARIO_VERSION_ID",
    "SITE_ID",
    "TASKS",
    "WORKERS",
    "infeasible_scheduler",
    "hard_constraint_failure_scheduler",
]
