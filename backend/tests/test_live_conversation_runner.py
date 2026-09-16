from evals.live_conversations.runner import (
    compact_reload_effect, relevant_entities, same_assignments, supplied_citation_ids,
)


def test_citation_ids_are_limited_to_explicit_identifiers_in_supplied_data():
    value = {'id': 'turn-1', 'assistant': [{'result_id': 'result-1', 'text': 'not-an-id'}],
             'facts': {'worker_id': 'worker-1', 'worker_name': 'Minh'}}
    assert supplied_citation_ids(value) == {'turn-1', 'result-1', 'worker-1'}


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


def test_assignment_comparison_ignores_order_and_transport_only_fields():
    projected = [
        {'worker_id': 'w2', 'task_id': 't2', 'start': '2026-01-02', 'end': '2026-01-03',
         'record_id': 'projection-row-2'},
        {'worker_id': 'w1', 'task_id': 't1', 'start': '2026-01-01', 'end': '2026-01-02',
         'record_id': 'projection-row-1'},
    ]
    candidate = [
        {'worker_id': 'w1', 'task_id': 't1', 'start': '2026-01-01', 'end': '2026-01-02'},
        {'worker_id': 'w2', 'task_id': 't2', 'start': '2026-01-02', 'end': '2026-01-03'},
    ]
    assert same_assignments(projected, candidate)
    candidate[0]['worker_id'] = 'different'
    assert not same_assignments(projected, candidate)


def test_judge_receives_only_entities_named_in_visible_reply():
    activity = {'activity_type': 'agent_response', 'response': {'segments': [
        {'kind': 'prose', 'text': 'Jae is assigned to Packing.'},
    ]}}
    workers = [
        {'record_id': 'w1', 'name': 'Jae', 'qualifications': [{'task_id': 't1', 'rate': 2}]},
        {'record_id': 'w2', 'name': 'Minh', 'qualifications': []},
    ]
    tasks = [
        {'record_id': 't1', 'task_id': 't1', 'name': 'Packing', 'function': 'Outbound'},
        {'record_id': 't2', 'task_id': 't2', 'name': 'Loading', 'function': 'Inbound'},
    ]
    assignments = [{'record_id': 'a1', 'worker_id': 'w1', 'task_id': 't1'}]
    assert relevant_entities(activity, workers, tasks, assignments) == {
        'named_workers': [{'record_id': 'w1', 'name': 'Jae', 'qualified_task_ids': ['t1']}],
        'named_tasks': [{'record_id': 't1', 'task_id': 't1', 'name': 'Packing',
                         'function': 'Outbound'}],
        'named_assignments': [{'record_id': 'a1', 'worker_id': 'w1', 'worker_name': 'Jae',
                               'task_id': 't1', 'task_name': 'Packing'}],
    }
