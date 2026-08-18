from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from uuid import UUID

import pytest

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_draft import (
    InvalidQueryError,
    SchedulingDraftRequestV1,
    derive_draft_id,
    scheduling_draft,
    scheduling_draft_manifest,
    scheduling_draft_module,
)
from application.contracts.agent_runtime import AgentBudgetV1
from application.contracts.proposal import DraftConstraintProposalV1
from application.contracts.scenario_projection import LockV1, ScenarioOverviewV1, TaskV1, WorkerV1
from application.ports.scenario_projection import LockPageV1


SITE = UUID(int=1)
SCENARIO = UUID(int=2)
VERSION = UUID(int=3)


class ProjectionStub:
    def __init__(self, *, locks: tuple[LockV1, ...] = ()) -> None:
        self.locks = locks
        self.task = TaskV1("task-1", "task-1", "Picking", "Pick", "area-1", "Area 1", None)
        self.worker = WorkerV1("worker-1", "worker-1", "Alex", "FT", "1", "EBA", 38.0, (), ())

    def get_overview(self, _connection, _scenario_id):
        return ScenarioOverviewV1(
            scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
            fixture_id="fixture", scenario_name="Scenario", fixture_version="v1",
            checksum_algorithm="sha256", checksum_schema_version="rfc8785-v1",
            checksum_digest="a" * 64,
            horizon_start=datetime(2026, 8, 18, tzinfo=timezone.utc),
            site_timezone="UTC", horizon_minutes=10080,
            baseline_schedule_version=None,
            projection_generated_at=datetime(2026, 8, 18, tzinfo=timezone.utc),
            work_area_count=1, task_count=1, worker_count=1, demand_interval_count=0,
            baseline_assignment_count=0, lock_count=len(self.locks), constraint_count=0,
        )

    def get_locks(self, _connection, _scenario_id, query):
        items = self.locks[query.cursor : query.cursor + query.limit]
        cursor = query.cursor + len(items)
        return LockPageV1(
            scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
            items=items, next_cursor=None if cursor >= len(self.locks) else cursor,
            total_count=len(self.locks), matching_count=len(self.locks),
        )

    def resolve_task(self, _connection, _scenario_id, version_id, record_id):
        return self._resolution(self.task, version_id, record_id)

    def resolve_worker(self, _connection, _scenario_id, version_id, record_id):
        return self._resolution(self.worker, version_id, record_id)

    @staticmethod
    def _resolution(item, version_id, record_id):
        if version_id != VERSION:
            return type("Resolution", (), {
                "outcome": "version_mismatch", "item": None,
                "current_scenario_version_id": VERSION,
            })()
        return type("Resolution", (), {
            "outcome": "resolved" if record_id == item.record_id else "not_found",
            "item": item if record_id == item.record_id else None,
            "current_scenario_version_id": VERSION,
        })()


def _deps(reader: ProjectionStub) -> AgentDepsV1:
    return AgentDepsV1(
        actor_id=UUID(int=4), site_id=SITE, membership_id=UUID(int=5),
        request_id=UUID(int=6), agent_run_id=UUID(int=7), conversation_id=UUID(int=8),
        scenario_id=SCENARIO, scenario_version_id=VERSION, policy_version="v1",
        clock=lambda: datetime(2026, 8, 18, tzinfo=timezone.utc),
        projection_reader=reader, connection=object(),
        remaining_budget=AgentBudgetV1(tool_calls_limit=2),
    )


def _request(*constraints: DraftConstraintProposalV1) -> SchedulingDraftRequestV1:
    return SchedulingDraftRequestV1(
        expected_scenario_version_id=VERSION,
        constraints=constraints,
    )


def test_capability_resolves_validates_preserves_real_locks_and_hides_details_from_model() -> None:
    reader = ProjectionStub(locks=(LockV1("lock-1", "worker", "worker-1", "week", "planner"),))
    request = _request(
        DraftConstraintProposalV1(
            kind="exclude_worker_from_task", group="workers", record_id="worker-1",
            related_group="work-areas-and-tasks", related_record_id="task-1",
        ),
        DraftConstraintProposalV1(
            kind="set_max_hours", group="workers", record_id="worker-1", max_hours=40.0,
        ),
    )

    result = scheduling_draft(_deps(reader), request)
    projected = scheduling_draft_module().model_facing_view(result)

    assert result.proposal.preserved_locks == reader.locks
    assert result.proposal.expected_baseline_schedule_version is None
    assert [entity.label for entity in result.proposal.resolved_entities] == [
        "Alex (worker-1)", "Picking (task-1)",
    ]
    assert result.result_id == derive_draft_id(
        VERSION, result.proposal.constraints, result.proposal.preserved_locks
    )
    assert asdict(projected) == {"draft_id": result.result_id, "schema_version": "1"}
    assert "scheduling_draft" == scheduling_draft_manifest().capability_name


@pytest.mark.parametrize(
    ("constraint", "message"),
    [
        (DraftConstraintProposalV1(kind="set_min_workers_per_task", record_id="missing", n=2), "missing"),
        (DraftConstraintProposalV1(kind="set_min_workers_per_task", record_id="task-1", n=0), "greater than 0"),
        (DraftConstraintProposalV1(kind="scale_demand", record_id="task-1", factor=0), "greater than 0"),
        (DraftConstraintProposalV1(kind="set_max_hours", group="workers", record_id="worker-1", max_hours=57), "56"),
        (DraftConstraintProposalV1(kind="lock_worker_shift", group="workers", record_id="worker-1", start_minute=60, end_minute=60), "end_minute"),
        (DraftConstraintProposalV1(kind="lock_worker_shift", group="workers", record_id="worker-1", start_minute=0, end_minute=10081), "horizon bound"),
        (DraftConstraintProposalV1(kind="set_max_hours", group="workers", record_id="worker-1", max_hours=40, n=2), "does not accept"),
    ],
)
def test_invalid_entities_and_ranges_fail_on_the_retryable_invalid_query_path(constraint, message) -> None:
    with pytest.raises(InvalidQueryError, match=message):
        scheduling_draft(_deps(ProjectionStub()), _request(constraint))


def test_draft_id_is_stable_and_sensitive_to_the_canonical_constraint() -> None:
    first = scheduling_draft(
        _deps(ProjectionStub()),
        _request(DraftConstraintProposalV1(record_id="task-1", n=2)),
    )
    replay = scheduling_draft(
        _deps(ProjectionStub()),
        _request(DraftConstraintProposalV1(record_id="task-1", n=2)),
    )
    changed = scheduling_draft(
        _deps(ProjectionStub()),
        _request(DraftConstraintProposalV1(record_id="task-1", n=3)),
    )
    assert first.result_id == replay.result_id
    assert first.result_id != changed.result_id
