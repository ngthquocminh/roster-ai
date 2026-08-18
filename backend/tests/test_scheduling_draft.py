from __future__ import annotations

import json
from dataclasses import asdict, replace
from pathlib import Path
from datetime import datetime, timezone
from uuid import UUID

import pytest

from application.capabilities.deps import AgentDepsV1
from application.capabilities.scheduling_draft import (
    InvalidQueryError,
    SchedulingDraftError,
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
from evals.fixture_projection import FIXTURE_IDENTITY, FixtureProjectionReader


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
        (DraftConstraintProposalV1(kind="set_max_hours", group="workers", record_id="worker-1", max_hours=57), "flat upper bound of 56"),
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


def test_the_citation_is_content_addressed_but_the_row_identity_is_not() -> None:
    """Two identical drafts share a draft_id and never share a proposal_id.

    Content-addressing exists so a golden case can cite the draft. Reusing it as
    the durable primary key made a legitimately repeated request an INSERT
    conflict that aborted the finalisation transaction and stranded the agent
    run in `agent_running`.
    """
    first = scheduling_draft(
        _deps(ProjectionStub()),
        _request(DraftConstraintProposalV1(record_id="task-1", n=2)),
    )
    repeat = scheduling_draft(
        _deps(ProjectionStub()),
        _request(DraftConstraintProposalV1(record_id="task-1", n=2)),
    )

    assert first.result_id == repeat.result_id
    assert first.proposal.canonical_hash == repeat.proposal.canonical_hash
    assert first.proposal.proposal_id != repeat.proposal.proposal_id
    assert first.proposal.proposal_version_id != repeat.proposal.proposal_version_id


def test_the_draft_and_revise_paths_canonicalize_through_one_hasher() -> None:
    """AD-20 fixes ONE hash rule, so there must be one implementation of it.

    `manage_proposal.revise_proposal` builds its `canonical_hash` from the same
    `derive_draft_id` the capability uses; this pins that they agree on identical
    trusted input, which two separately-maintained serializers would not.
    """
    result = scheduling_draft(
        _deps(ProjectionStub(locks=(LockV1("lock-1", "worker", "worker-1", "week", "planner"),))),
        _request(DraftConstraintProposalV1(record_id="task-1", n=4)),
    )
    assert result.proposal.canonical_hash == derive_draft_id(
        result.proposal.scenario_version_id,
        result.proposal.constraints,
        result.proposal.preserved_locks,
    )


def test_a_slow_resolution_is_bounded_rather_than_discarded_after_the_fact() -> None:
    """The budget must interrupt the work, not grade it once it has finished.

    Measuring elapsed time only after every projection read completed meant a
    hung reader ran to completion and the check then threw away a valid result.
    """
    reader = ProjectionStub()
    ticks = iter([datetime(2026, 8, 18, second=n, tzinfo=timezone.utc) for n in range(0, 60, 6)])
    last = {"value": datetime(2026, 8, 18, tzinfo=timezone.utc)}

    def creeping_clock():
        try:
            last["value"] = next(ticks)
        except StopIteration:
            pass
        return last["value"]

    deps = replace(_deps(reader), clock=creeping_clock)
    request = _request(
        *[DraftConstraintProposalV1(record_id="task-1", n=index + 1) for index in range(5)]
    )
    with pytest.raises(SchedulingDraftError) as raised:
        scheduling_draft(deps, request)
    assert "budget" in str(raised.value)
    # Retryable: the model can shrink the request and try again inside the run.
    assert raised.value.code in scheduling_draft_module().retryable_error_codes


def test_an_overlong_lock_page_is_refused_rather_than_driving_the_ceiling_negative() -> None:
    class OverlongLocks(ProjectionStub):
        def get_locks(self, _connection, _scenario_id, query):
            return LockPageV1(
                scenario_id=SCENARIO, scenario_version_id=VERSION, site_id=SITE,
                items=tuple(
                    LockV1(f"lock-{index}", "worker", "worker-1", "week", "planner")
                    for index in range(query.limit + 5)
                ),
                next_cursor=None, total_count=query.limit + 5,
                matching_count=query.limit + 5,
            )

    with pytest.raises(SchedulingDraftError, match="for a limit of"):
        scheduling_draft(_deps(OverlongLocks()), _request(
            DraftConstraintProposalV1(record_id="task-1", n=2)
        ))


def test_every_failure_golden_case_really_refuses_its_own_arguments() -> None:
    """Gap 2's posture: the refusal is tested, not asserted by a case's prose.

    The three failure cases each declare `expected_outcome: "refuse"`, but a
    scripted refusal proves only that the model said so. This drives each case's
    OWN arguments through the real capability and requires it to raise, so the
    dataset cannot stay green if the validation is deleted.
    """
    golden = Path(__file__).resolve().parents[1] / "evals" / "golden" / "scheduling_draft"
    reader = FixtureProjectionReader()
    overview = reader.get_overview(None, FIXTURE_IDENTITY)
    checked = 0
    for name in ("unresolvable-entity", "out-of-range-argument", "stale-version"):
        case = json.loads((golden / f"{name}.json").read_text(encoding="utf-8"))
        raw = case["scripted_turns"][0]["arguments"]["request"]
        request = SchedulingDraftRequestV1(
            expected_scenario_version_id=UUID(raw["expected_scenario_version_id"]),
            constraints=tuple(
                DraftConstraintProposalV1(
                    kind=item["kind"], group=item["group"], record_id=item["record_id"],
                    related_group=item["related_group"],
                    related_record_id=item["related_record_id"],
                    n=item["n"], factor=item["factor"], max_hours=item["max_hours"],
                    start_minute=item["start_minute"], end_minute=item["end_minute"],
                )
                for item in raw["constraints"]
            ),
        )
        deps = AgentDepsV1(
            actor_id=UUID(int=4), site_id=overview.site_id, membership_id=UUID(int=5),
            request_id=UUID(int=6), agent_run_id=UUID(int=7), conversation_id=UUID(int=8),
            scenario_id=overview.scenario_id,
            scenario_version_id=overview.scenario_version_id,
            policy_version="v1",
            clock=lambda: datetime(2026, 8, 18, tzinfo=timezone.utc),
            projection_reader=reader, connection=None,
            remaining_budget=AgentBudgetV1(tool_calls_limit=2),
        )
        with pytest.raises(InvalidQueryError):
            scheduling_draft(deps, request)
        checked += 1
    assert checked == 3


def test_the_valid_golden_case_cites_the_draft_id_the_capability_actually_produces() -> None:
    """The cited hash is measured, never hand-typed.

    `draft_id` had to be content-addressed precisely so a case could cite it; if
    the canonical form of a constraint ever changes, this fails here with the
    replacement value rather than failing obscurely inside the citation binding.
    """
    golden = Path(__file__).resolve().parents[1] / "evals" / "golden" / "scheduling_draft"
    case = json.loads((golden / "valid.json").read_text(encoding="utf-8"))
    raw = case["scripted_turns"][0]["arguments"]["request"]
    cited = case["scripted_turns"][1]["response_data"]["draft_id"]

    reader = FixtureProjectionReader()
    overview = reader.get_overview(None, FIXTURE_IDENTITY)
    deps = AgentDepsV1(
        actor_id=UUID(int=4), site_id=overview.site_id, membership_id=UUID(int=5),
        request_id=UUID(int=6), agent_run_id=UUID(int=7), conversation_id=UUID(int=8),
        scenario_id=overview.scenario_id,
        scenario_version_id=overview.scenario_version_id,
        policy_version="v1",
        clock=lambda: datetime(2026, 8, 18, tzinfo=timezone.utc),
        projection_reader=reader, connection=None,
        remaining_budget=AgentBudgetV1(tool_calls_limit=2),
    )
    result = scheduling_draft(
        deps,
        SchedulingDraftRequestV1(
            expected_scenario_version_id=UUID(raw["expected_scenario_version_id"]),
            constraints=tuple(
                DraftConstraintProposalV1(
                    kind=item["kind"], group=item["group"], record_id=item["record_id"],
                    related_group=item["related_group"],
                    related_record_id=item["related_record_id"],
                    n=item["n"], factor=item["factor"], max_hours=item["max_hours"],
                    start_minute=item["start_minute"], end_minute=item["end_minute"],
                )
                for item in raw["constraints"]
            ),
        ),
    )
    assert result.result_id == cited
    # The case asserts the APPLICATION-composed summary, not model prose.
    assert case["expected_visible_text"] == result.proposal.consequence_summary
