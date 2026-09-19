from dataclasses import replace
from types import SimpleNamespace
from uuid import UUID

from application.contracts.activity import DraftActivityV1
from application.contracts.proposal import ProposalV1
from application.contracts.schedule_version import ScheduleVersionV1
from application.contracts.scenario_projection import AssignmentV1, TaskV1, WorkerV1
from application.ports.proposal import ProposalRecordV1
from application.ports.schedule_run import ScheduleRunPageV1, ScheduleRunSummaryV1
from application.ports.scenario_projection import TaskPageV1, WorkerPageV1
from application.use_cases.conversation_workflow_context import load_workflow_context
from tests.test_execute_turn_use_case import NOW, _deps


def setup_context():
    deps = _deps()
    draft = DraftActivityV1(activity_id=UUID(int=20), activity_type='draft',
        conversation_id=deps.conversation_id, conversation_resource_version=3,
        scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
        occurred_at=NOW, proposal_id=UUID(int=21), proposal_version_id=UUID(int=22),
        consequence_summary='One constraint')
    claimed = SimpleNamespace(history=(draft,), site_id=deps.site_id,
        scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
        conversation_id=deps.conversation_id)
    proposal = ProposalV1(proposal_id=draft.proposal_id, proposal_version_id=draft.proposal_version_id,
        scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id)
    run = ScheduleRunSummaryV1(schedule_run_id=UUID(int=23), status='solver_completed',
        reason=None, resource_version=3, created_at=NOW, updated_at=NOW, finished_at=NOW,
        scenario_version_id=deps.scenario_version_id, proposal_id=draft.proposal_id,
        proposal_version=1, baseline_schedule_version=None)
    candidate = ScheduleVersionV1(schedule_version_id=UUID(int=24), schedule_run_id=run.schedule_run_id,
        scenario_id=deps.scenario_id, scenario_version_id=deps.scenario_version_id,
        feasible_solver_status='FEASIBLE')
    proposals = SimpleNamespace(get_current=lambda *a, **k: ProposalRecordV1(proposal, 1, deps.actor_id))
    runs = SimpleNamespace(
        list_runs=lambda *a, **k: ScheduleRunPageV1((run,), None, 1, 1),
        get_conversation_for_run=lambda *a, **k: deps.conversation_id,
        get_candidate=lambda *a, **k: candidate)
    baselines = SimpleNamespace(get=lambda *a: None)
    return claimed, proposals, runs, baselines, run, candidate


def test_context_reports_real_completed_candidate_after_manual_run():
    claimed, proposals, runs, baselines, run, candidate = setup_context()
    message = load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs, baselines=baselines)
    text = message.parts[0].text
    assert str(run.schedule_run_id) in text
    assert str(candidate.schedule_version_id) in text
    assert 'solver_completed' in text and 'FEASIBLE' in text
    assert 'not approval grants' in text


def test_context_excludes_runs_from_another_conversation():
    claimed, proposals, runs, baselines, run, _ = setup_context()
    runs.get_conversation_for_run = lambda *a, **k: UUID(int=999)
    text = load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs,
                                 baselines=baselines).parts[0].text
    assert str(run.schedule_run_id) not in text


def test_context_checks_candidate_immutable_pin():
    import pytest
    claimed, proposals, runs, baselines, _, candidate = setup_context()
    runs.get_candidate = lambda *a, **k: replace(candidate, scenario_version_id=UUID(int=999))
    with pytest.raises(ValueError, match='scenario pin'):
        load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs, baselines=baselines)


def test_no_draft_still_reports_current_baseline_state():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    text = load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs,
                                 baselines=baselines).parts[0].text
    assert '"baseline_schedule_version": null' in text
    assert '"baseline_assignments": []' in text
    assert f'"current_scenario_version_id": "{claimed.scenario_version_id}"' in text


def test_baseline_snapshot_joins_assignment_to_worker_and_task_labels():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    assignment = AssignmentV1('a1', 'w1', 't1', 's1', 0, 60)
    schedule = ScheduleVersionV1(schedule_version_id=UUID(int=30), scenario_id=claimed.scenario_id,
        scenario_version_id=claimed.scenario_version_id, assignments=(assignment,))
    baselines.get = lambda *a: SimpleNamespace(schedule_version_id=schedule.schedule_version_id)
    runs.get_version = lambda *a, **k: schedule
    worker = WorkerV1('w1', 'w1', 'Jae', 'FT', 'G1', 'E1', 38, (), ())
    task = TaskV1('t1', 't1', 'Packing', 'Outbound', 'area', 'Area', None)
    projection = SimpleNamespace(
        get_workers=lambda *a: WorkerPageV1(claimed.scenario_id, claimed.scenario_version_id,
            claimed.site_id, (worker,), None, 1, 1),
        get_tasks=lambda *a: TaskPageV1(claimed.scenario_id, claimed.scenario_version_id,
            claimed.site_id, (task,), None, 1, 1))
    text = load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs,
        baselines=baselines, projection=projection).parts[0].text
    assert '"worker_name": "Jae"' in text
    assert '"task_name": "Packing"' in text
    assert '"task_function": "Outbound"' in text


def test_baseline_snapshot_is_limited_to_ten_assignments_and_marks_truncation():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    assignments = tuple(AssignmentV1(f'a{index}', 'w1', 't1', 's1', index, index + 1)
                        for index in range(11))
    schedule = ScheduleVersionV1(schedule_version_id=UUID(int=31), scenario_id=claimed.scenario_id,
        scenario_version_id=claimed.scenario_version_id, assignments=assignments)
    baselines.get = lambda *a: SimpleNamespace(schedule_version_id=schedule.schedule_version_id)
    runs.get_version = lambda *a, **k: schedule
    worker = WorkerV1('w1', 'w1', 'Jae', 'FT', 'G1', 'E1', 38, (), ())
    task = TaskV1('t1', 't1', 'Packing', 'Outbound', 'area', 'Area', None)
    projection = SimpleNamespace(
        get_workers=lambda *a: WorkerPageV1(claimed.scenario_id, claimed.scenario_version_id,
            claimed.site_id, (worker,), None, 1, 1),
        get_tasks=lambda *a: TaskPageV1(claimed.scenario_id, claimed.scenario_version_id,
            claimed.site_id, (task,), None, 1, 1))
    text = load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs,
        baselines=baselines, projection=projection).parts[0].text
    assert text.count('"assignment_id":') == 10
    assert '"baseline_assignments_truncated": true' in text


# --- the loader's truncation and fail-closed branches --------------------------

import pytest


def _draft_activity(claimed, index):
    return DraftActivityV1(activity_id=UUID(int=500 + index), activity_type='draft',
        conversation_id=claimed.conversation_id, conversation_resource_version=index + 1,
        scenario_id=claimed.scenario_id, scenario_version_id=claimed.scenario_version_id,
        occurred_at=NOW, proposal_id=UUID(int=600 + index), proposal_version_id=UUID(int=700 + index),
        consequence_summary='c')


def _load(claimed, proposals, runs, baselines, projection=None):
    return load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs,
                                 baselines=baselines, projection=projection).parts[0].text


def _with_baseline(claimed, runs, baselines, *, assignment_count=1, schedule_scenario_id=None,
                   workers=True, tasks=True, more_workers=False):
    assignments = tuple(AssignmentV1(f'a{i}', 'w1', 't1', 's1', i, i + 1) for i in range(assignment_count))
    schedule = ScheduleVersionV1(schedule_version_id=UUID(int=40),
        scenario_id=schedule_scenario_id or claimed.scenario_id,
        scenario_version_id=claimed.scenario_version_id, assignments=assignments)
    baselines.get = lambda *a: SimpleNamespace(schedule_version_id=schedule.schedule_version_id)
    runs.get_version = lambda *a, **k: schedule
    worker = WorkerV1('w1', 'w1', 'Jae', 'FT', 'G1', 'E1', 38, (), ())
    task = TaskV1('t1', 't1', 'Packing', 'Outbound', 'area', 'Area', None)
    return SimpleNamespace(
        get_workers=lambda *a: (WorkerPageV1(claimed.scenario_id, claimed.scenario_version_id,
            claimed.site_id, (worker,), 'next' if more_workers else None, 1, 1) if workers else None),
        get_tasks=lambda *a: (TaskPageV1(claimed.scenario_id, claimed.scenario_version_id,
            claimed.site_id, (task,), None, 1, 1) if tasks else None))


def test_exactly_ten_baseline_assignments_are_not_reported_as_truncated():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines, assignment_count=10)
    text = _load(claimed, proposals, runs, baselines, projection)
    assert text.count('"assignment_id":') == 10
    assert '"baseline_assignments_truncated": false' in text


def test_an_unfinished_label_page_marks_the_baseline_snapshot_truncated():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines, more_workers=True)
    assert '"baseline_assignments_truncated": true' in _load(claimed, proposals, runs, baselines, projection)


def test_an_assignment_whose_worker_or_task_is_unknown_keeps_its_ids_and_no_names():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines)
    projection.get_workers = lambda *a: WorkerPageV1(claimed.scenario_id, claimed.scenario_version_id,
        claimed.site_id, (), None, 0, 0)
    text = _load(claimed, proposals, runs, baselines, projection)
    assert '"worker_id": "w1"' in text and '"worker_name": null' in text


def test_a_baseline_from_another_scenario_contributes_no_assignments():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    _with_baseline(claimed, runs, baselines, schedule_scenario_id=UUID(int=999))
    # No projection is passed: a foreign baseline must not even need one.
    text = _load(claimed, proposals, runs, baselines, projection=None)
    assert '"baseline_assignments": []' in text


@pytest.mark.parametrize('breakage,message', [
    ('dangling', 'baseline schedule unavailable'),
    ('no_projection', 'projection reader required'),
    ('no_workers', 'baseline labels unavailable'),
    ('no_tasks', 'baseline labels unavailable'),
])
def test_a_baseline_the_loader_cannot_describe_fails_closed_with_a_value_error(breakage, message):
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines, workers=breakage != 'no_workers',
                                tasks=breakage != 'no_tasks')
    if breakage == 'dangling':
        runs.get_version = lambda *a, **k: None
    if breakage == 'no_projection':
        projection = None
    with pytest.raises(ValueError, match=message):
        _load(claimed, proposals, runs, baselines, projection)


def test_more_than_ten_drafts_keeps_the_latest_ten_and_says_it_truncated():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = tuple(_draft_activity(claimed, i) for i in range(11))
    seen = []

    def get_current(_connection, *, proposal_id):
        seen.append(proposal_id)
        return None

    proposals.get_current = get_current
    text = _load(claimed, proposals, runs, baselines)
    assert seen == [UUID(int=600 + i) for i in range(1, 11)]
    assert '"drafts_truncated": true' in text


def test_a_draft_outside_the_hundred_activity_window_still_marks_drafts_truncated():
    claimed, proposals, runs, baselines, *_ = setup_context()
    filler = tuple(SimpleNamespace(activity_type='planner_message') for _ in range(100))
    claimed.history = (_draft_activity(claimed, 0), *filler)
    assert '"drafts_truncated": true' in _load(claimed, proposals, runs, baselines)
    claimed.history = (*filler, _draft_activity(claimed, 0))
    assert '"drafts_truncated": false' in _load(claimed, proposals, runs, baselines)


def test_a_missing_or_foreign_draft_is_skipped_not_reported():
    claimed, proposals, runs, baselines, *_ = setup_context()
    record = proposals.get_current()
    proposals.get_current = lambda *a, **k: None
    assert '"drafts": []' in _load(claimed, proposals, runs, baselines)
    foreign = replace(record.proposal, scenario_version_id=UUID(int=999))
    proposals.get_current = lambda *a, **k: replace(record, proposal=foreign)
    assert '"drafts": []' in _load(claimed, proposals, runs, baselines)


def test_a_run_pinned_to_another_scenario_version_is_skipped():
    claimed, proposals, runs, baselines, run, _ = setup_context()
    other = replace(run, scenario_version_id=UUID(int=999))
    runs.list_runs = lambda *a, **k: ScheduleRunPageV1((other,), None, 1, 1)
    assert str(run.schedule_run_id) not in _load(claimed, proposals, runs, baselines)


def test_a_candidate_for_another_scenario_fails_closed():
    claimed, proposals, runs, baselines, _, candidate = setup_context()
    runs.get_candidate = lambda *a, **k: replace(candidate, scenario_id=UUID(int=999))
    with pytest.raises(ValueError, match='scenario pin'):
        _load(claimed, proposals, runs, baselines)


def test_a_candidate_lists_five_assignments_and_says_when_it_holds_more():
    claimed, proposals, runs, baselines, _, candidate = setup_context()
    rows = tuple(AssignmentV1(f'c{i}', 'w1', 't1', 's1', i, i + 1) for i in range(6))
    runs.get_candidate = lambda *a, **k: replace(candidate, assignments=rows)
    text = _load(claimed, proposals, runs, baselines)
    assert '"assignment_count": 6' in text and '"assignments_truncated": true' in text
    assert text.count('"record_id": "c') == 5
    runs.get_candidate = lambda *a, **k: replace(candidate, assignments=rows[:5])
    assert '"assignments_truncated": false' in _load(claimed, proposals, runs, baselines)


def test_an_unfinished_run_page_is_reported_as_truncated():
    claimed, proposals, runs, baselines, run, _ = setup_context()
    runs.list_runs = lambda *a, **k: ScheduleRunPageV1((run,), 20, 1, 1)
    assert '"runs_truncated": true' in _load(claimed, proposals, runs, baselines)
    runs.list_runs = lambda *a, **k: ScheduleRunPageV1((run,), None, 1, 1)
    assert '"runs_truncated": false' in _load(claimed, proposals, runs, baselines)
