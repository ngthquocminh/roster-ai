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
