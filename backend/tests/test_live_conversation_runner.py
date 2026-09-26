import pytest

from evals.live_conversations.judge import PAYLOAD_STRUCTURE_KEYS
from evals.live_conversations.runner import (
    compact_reload_effect, known_citation_ids, relevant_entities, same_assignments,
    supplied_citation_ids,
)


def test_citation_ids_are_limited_to_explicit_identifiers_in_supplied_data():
    value = {'id': 'turn-1', 'assistant': [{'result_id': 'result-1', 'text': 'not-an-id'}],
             'facts': {'worker_id': 'worker-1', 'worker_name': 'Minh'}}
    assert supplied_citation_ids(value) == {'turn-1', 'result-1', 'worker-1'}


def test_known_citation_ids_accepts_a_scalar_facts_own_group_name():
    verified = {'id': 'turn-1:facts', 'candidate_solver_status': 'FEASIBLE',
                'latest_run': {'schedule_run_id': 'run-1'}}
    known = known_citation_ids([], verified, 'turn-1:obligation')
    assert known == ({'turn-1:facts', 'run-1', 'candidate_solver_status', 'latest_run',
                      'turn-1:obligation', 'id'} | PAYLOAD_STRUCTURE_KEYS)


def test_reload_effect_keeps_only_visible_identity_and_activity_types():
    compact = compact_reload_effect({
        'items': [
            {'activity_id': 'one', 'activity_type': 'agent_response',
             'response': {'segments': [{'kind': 'prose', 'text': 'secret-sized-content'}]}},
            {'activity_id': 'two', 'activity_type': 'draft', 'proposal_id': 'proposal'},
        ],
        'has_more': False,
        'internal_future_field': {'must': 'not be forwarded'},
    })
    assert compact == {
        'has_more': False,
        'visible_activities': [
            {'activity_id': 'one', 'activity_type': 'agent_response'},
            {'activity_id': 'two', 'activity_type': 'draft'},
        ],
    }


def _row(worker, task, start, end, shift=None, **transport):
    return {'worker_id': worker, 'task_id': task, 'shift_id': shift,
            'start_minute': start, 'end_minute': end, **transport}


def test_assignment_comparison_ignores_order_and_transport_only_fields():
    projected = [_row('w2', 't2', 60, 120, record_id='projection-row-2'),
                 _row('w1', 't1', 0, 60, record_id='projection-row-1')]
    candidate = [_row('w1', 't1', 0, 60), _row('w2', 't2', 60, 120)]
    assert same_assignments(projected, candidate)
    candidate[0]['worker_id'] = 'different'
    assert not same_assignments(projected, candidate)


@pytest.mark.parametrize('field,value', [('start_minute', 30), ('end_minute', 90), ('shift_id', 's9'),
                                         ('task_id', 't9')])
def test_a_difference_in_any_compared_field_alone_is_a_mismatch(field, value):
    # The promoted baseline must be EXACTLY the approved candidate: a wrong time
    # with the right worker and task is still a wrong baseline.
    projected = [_row('w1', 't1', 0, 60)]
    assert same_assignments(projected, [_row('w1', 't1', 0, 60)])
    assert not same_assignments(projected, [{**_row('w1', 't1', 0, 60), field: value}])


def test_assignment_comparison_counts_rows_not_just_distinct_values():
    row = _row('w1', 't1', 0, 60)
    assert not same_assignments([row], [row, row])
    assert not same_assignments([row, row], [row])
    assert not same_assignments([row, row], [row, _row('w1', 't1', 0, 61)])
    assert same_assignments([], [])


def test_assignment_comparison_orders_rows_whose_shift_is_none_on_one_side_only():
    # sorted() over these tuples raised TypeError (None vs str at the same worker
    # and task); the comparison must report a mismatch or a match, never crash.
    with_shift = [_row('w1', 't1', 0, 60, shift='s1'), _row('w1', 't1', 60, 120)]
    assert same_assignments(with_shift, list(reversed(with_shift)))
    assert not same_assignments(with_shift, [_row('w1', 't1', 0, 60), _row('w1', 't1', 60, 120)])


def test_judge_receives_only_entities_named_in_visible_reply():
    activity = {'activity_type': 'agent_response', 'response': {'segments': [
        {'kind': 'prose', 'text': 'Mika is assigned to Packing.'},
    ]}}
    workers = [
        {'record_id': 'w1', 'name': 'Mika', 'employment_type': 'Full Time',
         'grade': 'G3', 'eba': 'E1', 'contracted_hours': 40,
         'qualifications': [{'task_id': 't1', 'rate': 2}],
         'availability_windows': [{'kind': 'roster'}, {'kind': 'availability'}]},
        {'record_id': 'w2', 'name': 'Minh', 'qualifications': []},
    ]
    tasks = [
        {'record_id': 't1', 'task_id': 't1', 'name': 'Packing', 'function': 'Outbound'},
        {'record_id': 't2', 'task_id': 't2', 'name': 'Loading', 'function': 'Inbound'},
    ]
    assignments = [{'record_id': 'a1', 'worker_id': 'w1', 'task_id': 't1'}]
    demand = [{'task_id': 't1', 'family': 'outbound'}, {'task_id': 't1', 'family': 'outbound'}]
    assert relevant_entities(activity, workers, tasks, assignments, demand) == {
        'named_workers': [{'record_id': 'w1', 'name': 'Mika',
                           'employment_type': 'Full Time', 'grade': 'G3', 'eba': 'E1',
                           'contracted_hours': 40, 'qualified_task_ids': ['t1'],
                           'roster_window_count': 1,
                           'extra_availability_window_count': 1}],
        'named_tasks': [{'record_id': 't1', 'task_id': 't1', 'name': 'Packing',
                         'function': 'Outbound', 'demand_families': ['outbound']}],
        'named_assignments': [{'record_id': 'a1', 'worker_id': 'w1', 'worker_name': 'Mika',
                               'task_id': 't1', 'task_name': 'Packing'}],
    }


def test_named_task_with_no_demand_rows_reports_no_family():
    activity = {'activity_type': 'agent_response', 'response': {'segments': [
        {'kind': 'prose', 'text': 'Loading has no demand rows.'},
    ]}}
    tasks = [{'record_id': 't2', 'task_id': 't2', 'name': 'Loading', 'function': 'Inbound'}]
    result = relevant_entities(activity, [], tasks, [], demand=())
    assert result['named_tasks'] == [{'record_id': 't2', 'task_id': 't2', 'name': 'Loading',
                                      'function': 'Inbound', 'demand_families': []}]
