import json
from dataclasses import asdict, replace
from types import SimpleNamespace
from uuid import UUID

from application.contracts.activity import DraftActivityV1
from application.contracts.proposal import ProposalV1
from application.contracts.schedule_version import ConstraintResultV1, MetricSetV1, ScheduleVersionV1
from application.contracts.scenario_projection import AssignmentV1, TaskV1
from application.ports.proposal import ProposalRecordV1
from application.ports.schedule_run import ScheduleRunPageV1, ScheduleRunSummaryV1
from application.ports.scenario_projection import TaskPageV1
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
    proposals = SimpleNamespace(get_current=lambda *a, **k: ProposalRecordV1(proposal, 1, deps.actor_id),
        get_working=lambda *a, **k: None, get_version=lambda *a, **k: None,
        get_version_at=lambda *a, **k: None)
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
    assert '"baseline_summary": null' in text
    assert f'"current_scenario_version_id": "{claimed.scenario_version_id}"' in text


def test_baseline_snapshot_summarises_the_whole_baseline_and_lists_no_assignments():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines, assignment_count=11)
    text = _load(claimed, proposals, runs, baselines, projection)
    summary = _facts(text)['baseline_summary']
    assert summary['applies_to_this_scenario_version'] is True
    assert summary['assignment_count'] == 11
    assert summary['workers_scheduled'] == 1 and summary['tasks_staffed'] == 1
    assert summary['staffed_minutes'] == 11
    assert summary['by_function'] == [
        {'function': 'Outbound', 'assignment_count': 11, 'staffed_minutes': 11}]
    assert summary['total_cost'] == 120.5 and summary['overtime_minutes'] == 30.0
    assert summary['solver_objective_components'] == {'unmet_minutes': 0.0}
    assert summary['hard_constraints'] == {'checked': 2, 'violated': ['max_shifts_per_day']}
    assert summary['soft_constraints'] == [{'constraint_type': 'set_max_hours', 'satisfied': True,
        'measured_value': 14.5, 'limit': 16.0, 'unit': 'hours'}]
    assert '"assignment_id"' not in text and 'baseline_assignments' not in text


# --- the loader's truncation and fail-closed branches --------------------------

import pytest


def _draft_activity(claimed, index):
    return DraftActivityV1(activity_id=UUID(int=500 + index), activity_type='draft',
        conversation_id=claimed.conversation_id, conversation_resource_version=index + 1,
        scenario_id=claimed.scenario_id, scenario_version_id=claimed.scenario_version_id,
        occurred_at=NOW, proposal_id=UUID(int=600 + index), proposal_version_id=UUID(int=700 + index),
        consequence_summary='c')


def _facts(text):
    return json.loads(text[text.index('\n') + 1:])


def _load(claimed, proposals, runs, baselines, projection=None):
    return load_workflow_context(None, claimed=claimed, proposals=proposals, runs=runs,
                                 baselines=baselines, projection=projection).parts[0].text


def _with_baseline(claimed, runs, baselines, *, assignment_count=1, schedule_scenario_id=None,
                   tasks=True, task_pages=1):
    assignments = tuple(AssignmentV1(f'a{i}', 'w1', 't1', 's1', i, i + 1) for i in range(assignment_count))
    schedule = ScheduleVersionV1(schedule_version_id=UUID(int=40),
        scenario_id=schedule_scenario_id or claimed.scenario_id,
        scenario_version_id=claimed.scenario_version_id, assignments=assignments,
        feasible_solver_status='FEASIBLE',
        metrics=MetricSetV1(total_cost=120.5, overtime_minutes=30.0,
                            objective_components=(('unmet_minutes', 0.0),)),
        constraint_results=(
            ConstraintResultV1('c1', 'one_shift_per_window', 'hard', True),
            ConstraintResultV1('c2', 'max_shifts_per_day', 'hard', False),
            ConstraintResultV1('c3', 'set_max_hours', 'soft', True, 14.5, 16.0, 'hours')))
    baselines.get = lambda *a: SimpleNamespace(schedule_version_id=schedule.schedule_version_id)
    runs.get_version = lambda *a, **k: schedule
    task = TaskV1('t1', 't1', 'Packing', 'Outbound', 'area', 'Area', None)
    filler = TaskV1('t2', 't2', 'Other', 'Pick', 'area', 'Area', None)

    def get_tasks(_connection, _scenario_id, query):
        # Pages of one task each; the last page has no cursor.
        index = query.cursor
        item = task if index == 0 else filler
        return TaskPageV1(claimed.scenario_id, claimed.scenario_version_id, claimed.site_id,
                          (item,), index + 1 if index + 1 < task_pages else None, task_pages, task_pages)

    return SimpleNamespace(get_tasks=get_tasks if tasks else (lambda *a: None))


def test_a_task_the_projection_does_not_know_is_reported_as_function_unknown():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines)
    projection.get_tasks = lambda *a: TaskPageV1(claimed.scenario_id, claimed.scenario_version_id,
        claimed.site_id, (), None, 0, 0)
    summary = _facts(_load(claimed, proposals, runs, baselines, projection))['baseline_summary']
    assert summary['by_function'][0]['function'] == 'unknown'


def test_task_functions_are_read_across_every_page_of_tasks():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines, task_pages=2)
    # Re-point the only assignment at the task that lives on page two.
    schedule = runs.get_version()
    runs.get_version = lambda *a, **k: replace(schedule,
        assignments=(AssignmentV1('a0', 'w1', 't2', 's1', 0, 1),))
    summary = _facts(_load(claimed, proposals, runs, baselines, projection))['baseline_summary']
    assert summary['by_function'][0]['function'] == 'Pick'


def test_a_baseline_from_another_scenario_is_reported_as_not_applying():
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    _with_baseline(claimed, runs, baselines, schedule_scenario_id=UUID(int=999))
    # No projection is passed: a foreign baseline must not even need one.
    facts = _facts(_load(claimed, proposals, runs, baselines, projection=None))
    assert facts['baseline_schedule_version'] is not None
    assert facts['baseline_summary'] == {'applies_to_this_scenario_version': False}


@pytest.mark.parametrize('breakage,message', [
    ('dangling', 'baseline schedule unavailable'),
    ('no_projection', 'projection reader required'),
    ('no_tasks', 'baseline labels unavailable'),
])
def test_a_baseline_the_loader_cannot_describe_fails_closed_with_a_value_error(breakage, message):
    claimed, proposals, runs, baselines, *_ = setup_context()
    claimed.history = ()
    projection = _with_baseline(claimed, runs, baselines, tasks=breakage != 'no_tasks')
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


# --- Story 5.11: the working draft and the ended drafts (Decision 12) ----------


def test_no_working_draft_reads_null_and_a_working_draft_reads_its_version_ordinal():
    claimed, proposals, runs, baselines, *_ = setup_context()
    assert _facts(_load(claimed, proposals, runs, baselines))['working_draft'] is None
    record = proposals.get_current()
    working = replace(record, proposal=replace(record.proposal, proposal_id=UUID(int=90)),
                      version_ordinal=3)
    proposals.get_working = lambda *a, **k: working
    facts = _facts(_load(claimed, proposals, runs, baselines))
    assert facts['working_draft']['proposal_id'] == str(UUID(int=90))
    assert facts['working_draft']['version_ordinal'] == 3
    assert facts['working_draft']['state'] == 'active'


def test_the_working_draft_is_present_even_when_its_activities_left_the_window():
    """Read from the repository, never inferred from history (mutation: history only)."""
    claimed, proposals, runs, baselines, *_ = setup_context()
    filler = tuple(SimpleNamespace(activity_type='planner_message') for _ in range(150))
    claimed.history = filler
    seen = []
    record = proposals.get_current()
    proposals.get_working = lambda *a, **k: seen.append(k) or record
    facts = _facts(_load(claimed, proposals, runs, baselines))
    assert facts['working_draft'] is not None
    assert seen == [{'conversation_id': claimed.conversation_id, 'for_update': False}]


def test_the_working_draft_is_not_repeated_among_the_ended_drafts():
    claimed, proposals, runs, baselines, *_ = setup_context()
    record = proposals.get_current()
    proposals.get_working = lambda *a, **k: record
    facts = _facts(_load(claimed, proposals, runs, baselines))
    assert facts['working_draft'] is not None
    assert facts['drafts'] == []


def test_the_working_drafts_own_old_activities_do_not_mark_drafts_truncated():
    """The working draft is reported directly, so its activities outside the
    100-activity window truncate nothing (Decision 12: the flag covers ended
    drafts). Mutation: count every old draft activity => this reddens (code
    review of story-5.11)."""
    claimed, proposals, runs, baselines, *_ = setup_context()
    record = proposals.get_current()
    working = replace(record, proposal=replace(record.proposal, proposal_id=UUID(int=600)))
    proposals.get_working = lambda *a, **k: working
    filler = tuple(SimpleNamespace(activity_type='planner_message') for _ in range(100))
    claimed.history = (_draft_activity(claimed, 0), *filler)
    assert '"drafts_truncated": false' in _load(claimed, proposals, runs, baselines)
    claimed.history = (_draft_activity(claimed, 0), _draft_activity(claimed, 1), *filler)
    assert '"drafts_truncated": true' in _load(claimed, proposals, runs, baselines)


def test_ended_drafts_carry_state_ended_by_and_version_ordinal():
    claimed, proposals, runs, baselines, *_ = setup_context()
    record = proposals.get_current()
    ended = replace(record, proposal=replace(record.proposal, state='rejected'),
                    ended_by='assistant', version_ordinal=4)
    proposals.get_current = lambda *a, **k: ended
    (draft,) = _facts(_load(claimed, proposals, runs, baselines))['drafts']
    assert (draft['state'], draft['ended_by'], draft['version_ordinal']) == ('rejected', 'assistant', 4)
    assert 'applied_version' not in draft


def test_an_applied_draft_reports_the_pinned_version_not_the_latest():
    from application.contracts.proposal import DraftConstraintV1
    claimed, proposals, runs, baselines, *_ = setup_context()
    record = proposals.get_current()
    latest = replace(record.proposal, state='applied', consequence_summary='v3 latest')
    applied_version_id = UUID(int=77)
    applied = replace(record.proposal, consequence_summary='v2 pinned',
        constraints=(DraftConstraintV1(kind='set_max_hours', max_hours=40.0, description='cap'),))
    proposals.get_current = lambda *a, **k: replace(
        record, proposal=latest, ended_by='system', version_ordinal=3,
        applied_version_id=applied_version_id, applied_version_ordinal=2)
    asked = []
    proposals.get_version = lambda *a, **k: asked.append(k['proposal_version_id']) or (2, applied)
    (draft,) = _facts(_load(claimed, proposals, runs, baselines))['drafts']
    assert asked == [applied_version_id]
    assert draft['state'] == 'applied' and draft['version_ordinal'] == 3
    assert draft['applied_version']['version_ordinal'] == 2
    assert draft['applied_version']['consequence_summary'] == 'v2 pinned'
    assert draft['applied_version']['constraints'][0]['max_hours'] == 40.0


def test_the_working_draft_carries_the_version_before_its_latest():
    """"Undo that" re-sends this list instead of rebuilding it from the chat
    (Story 5.12: live E:4 dropped the hours cap 2 runs in 5)."""
    claimed, proposals, runs, baselines, *_ = setup_context()
    record = proposals.get_current()
    working = replace(record, proposal=replace(record.proposal, proposal_id=UUID(int=91)),
                      version_ordinal=3)
    proposals.get_working = lambda *a, **k: working
    asked = []
    earlier = replace(record.proposal, proposal_id=UUID(int=91))
    proposals.get_version_at = lambda *a, **k: asked.append(k) or earlier
    facts = _facts(_load(claimed, proposals, runs, baselines))
    assert asked == [{'proposal_id': UUID(int=91), 'version_ordinal': 2}]
    assert facts['working_draft']['previous_version'] == {
        'version_ordinal': 2, 'constraints': json.loads(json.dumps(
            asdict(earlier)['constraints'], default=str))}


def test_a_first_version_has_no_previous_version():
    claimed, proposals, runs, baselines, *_ = setup_context()
    record = proposals.get_current()
    proposals.get_working = lambda *a, **k: record  # version_ordinal 1
    proposals.get_version_at = lambda *a, **k: pytest.fail('v1 has no earlier version')
    assert 'previous_version' not in _facts(_load(claimed, proposals, runs, baselines))['working_draft']
