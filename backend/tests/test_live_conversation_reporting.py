"""Right-sized AC7 verdict: clean run per scenario, three repetitions, no false claims."""
from evals.live_conversations.cases import load_scenarios, prefix_executions
from evals.live_conversations.reporting import summarize_runs

BINDING = {'code': {'git_commit': 'test-only', 'working_tree_dirty': False}}


def _run(number, *, verdicts=None, failures=None):
    verdicts, failures = verdicts or {}, failures or {}
    executions = []
    for case, _endpoint, turns in prefix_executions(load_scenarios()):
        rows = []
        for index, turn in enumerate(turns, 1):
            key = f'{case.id}:{index}'
            rows.append({'user': turn.user, 'verdict': verdicts.get(key, 'pass'),
                         'factual_failures': failures.get(key, [])})
        executions.append({
            'scenario': case.id, 'endpoint': len(turns),
            'conversation_id': f'{number}-{case.id}', 'isolation_id': f'{number}-{case.id}',
            'status': 'passed' if all(r['verdict'] == 'pass' for r in rows) else 'failed',
            'turns': rows,
        })
    return {'run_id': str(number), 'version_bindings': BINDING, 'prefixes': executions}


def _summary(runs, **kwargs):
    return summarize_runs(runs, coverage={}, observation_ids=set(), version_bindings=BINDING, **kwargs)


def test_missing_runs_cannot_become_eligible():
    report = summarize_runs([], coverage={}, observation_ids=set(), version_bindings={})
    assert report['readiness'] == 'blocked'
    assert report['live_conversation_journeys'] == 'blocked'
    assert report['required_scenarios_per_run'] == 3
    assert report['required_user_turns_per_run'] == 30


def test_three_clean_repetitions_meet_every_run_based_requirement():
    report = _summary([_run(i) for i in range(3)])
    # Only the coverage row (empty here) remains blocking.
    assert report['blocking_reasons'] == ['tool_operation_coverage_incomplete_or_stale']
    assert report['complete_repetitions'] == 3
    assert report['clean_scenarios'] == ['A', 'B', 'C']
    assert report['turn_pass_rates']['B:9'] == {'passed': 3, 'executed': 3}


def test_a_false_claim_in_any_counted_run_blocks():
    runs = [_run(0), _run(1), _run(2, verdicts={'B:4': 'fail'},
                                   failures={'B:4': ['required_persisted_draft_missing']})]
    report = _summary(runs, accepted_findings=[('B', 4)])
    assert 'false_claim_or_effect_failure' in report['blocking_reasons']
    assert report['false_claims'] == [{'run_id': '2', 'turn': 'B:4',
                                       'failures': ['required_persisted_draft_missing']}]


def test_a_reliability_failure_blocks_until_explicitly_accepted():
    runs = [_run(0), _run(1, verdicts={'C:3': 'fail'},
                          failures={'C:3': ['unsuccessful_agent_turn']}), _run(2)]
    blocked = _summary(runs)
    assert 'unaccepted_turn_failure' in blocked['blocking_reasons']
    assert blocked['turn_pass_rates']['C:3'] == {'passed': 2, 'executed': 3}
    accepted = _summary(runs, accepted_findings=[('C', 3)])
    assert 'unaccepted_turn_failure' not in accepted['blocking_reasons']
    assert 'false_claim_or_effect_failure' not in accepted['blocking_reasons']


def test_a_scenario_that_never_ran_clean_blocks():
    runs = [_run(i, verdicts={'B:2': 'fail'}) for i in range(3)]
    report = _summary(runs, accepted_findings=[('B', 2)])
    assert 'clean_run_missing_for_scenario' in report['blocking_reasons']
    assert report['clean_scenarios'] == ['A', 'C']


def test_incomplete_or_reused_executions_do_not_count_as_repetitions():
    partial = _run(1)
    partial['prefixes'] = partial['prefixes'][:-1]
    reused = _run(2)
    reused['prefixes'][0]['conversation_id'] = '0-A'
    report = _summary([_run(0), partial, reused])
    assert report['complete_repetitions'] == 1
    assert 'three_complete_repetitions_missing' in report['blocking_reasons']
