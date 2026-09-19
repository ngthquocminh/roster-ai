"""Right-sized AC7 verdict: clean run per scenario, three repetitions, no false claims."""
import pytest

from evals.live_conversations.cases import load_scenarios, prefix_executions
from evals.live_conversations.reporting import summarize_runs

BINDING = {'code': {'git_commit': 'test-only', 'working_tree_dirty': False}}


def _run(number, *, verdicts=None, failures=None, repetition=1):
    verdicts, failures = verdicts or {}, failures or {}
    executions = []
    for case, _endpoint, turns in prefix_executions(load_scenarios()):
        rows = []
        for index, turn in enumerate(turns, 1):
            key = f'{case.id}:{index}'
            rows.append({'user': turn.user, 'verdict': verdicts.get(key, 'pass'),
                         'factual_failures': failures.get(key, [])})
        executions.append({
            'scenario': case.id, 'endpoint': len(turns), 'repetition': repetition,
            'conversation_id': f'{number}-{case.id}', 'isolation_id': f'{number}-{case.id}',
            'status': 'passed' if all(r['verdict'] == 'pass' for r in rows) else 'failed',
            'turns': rows,
        })
    return {'run_id': str(number), 'code': BINDING['code'], 'prefixes': executions}


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


def test_a_refused_claim_blocks_until_that_turn_is_accepted():
    """The planner sees "Claim unavailable", never a wrong number, so this is
    inspectable and acceptable -- but only when named explicitly."""
    runs = [_run(0), _run(1), _run(2, verdicts={'C:5': 'fail'},
                                   failures={'C:5': ['unsupported_claim']})]
    assert 'false_claim_or_effect_failure' in _summary(runs)['blocking_reasons']
    accepted = _summary(runs, accepted_findings=[('C', 5)])
    assert 'false_claim_or_effect_failure' not in accepted['blocking_reasons']
    assert accepted['turn_pass_rates']['C:5'] == {'passed': 2, 'executed': 3}


def test_a_wrong_value_can_never_be_accepted():
    runs = [_run(0), _run(1), _run(2, verdicts={'C:5': 'fail'},
                                   failures={'C:5': ['incorrect_claim_value_or_unit']})]
    report = _summary(runs, accepted_findings=[('C', 5)])
    assert 'false_claim_or_effect_failure' in report['blocking_reasons']


# --- readiness branches that the cases above only touch indirectly -------------

def _reasons(runs, *, binding=BINDING, coverage=None, **kwargs):
    return summarize_runs(runs, coverage=coverage or {}, observation_ids=set(),
                          version_bindings=binding, **kwargs)['blocking_reasons']


def test_a_dirty_or_missing_version_binding_blocks_on_that_reason_alone():
    dirty = {'code': {'git_commit': 'test-only', 'working_tree_dirty': True}}
    runs = [{**_run(i), 'code': dirty['code']} for i in range(3)]
    assert 'clean_version_binding_missing' in _reasons(runs, binding=dirty)
    assert 'clean_version_binding_missing' in _reasons([_run(i) for i in range(3)], binding={})
    assert 'clean_version_binding_missing' not in _reasons([_run(i) for i in range(3)])


def test_a_run_measured_on_other_code_never_counts():
    other = {**_run(1), 'code': {'git_commit': 'someone-elses', 'working_tree_dirty': False}}
    report = _summary([_run(0), other, _run(2)])
    assert report['complete_repetitions'] == 2
    assert 'three_complete_repetitions_missing' in report['blocking_reasons']


def test_a_run_with_no_run_id_never_counts():
    anonymous = {**_run(1), 'run_id': ''}
    assert _summary([_run(0), anonymous, _run(2)])['complete_repetitions'] == 2


def test_one_report_carrying_three_repetitions_counts_each():
    combined = {'run_id': 'r', 'code': BINDING['code'], 'prefixes': [
        execution for repetition in (1, 2, 3)
        for execution in _run(repetition, repetition=repetition)['prefixes']]}
    report = _summary([combined])
    assert report['complete_repetitions'] == 3
    assert [summary['repetition'] for summary in report['runs']] == [1, 2, 3]
    assert report['turn_pass_rates']['A:1'] == {'passed': 3, 'executed': 3}


def _with_earlier_attempt(run, scenario, verdict):
    """The runner appends a retried execution AFTER the attempt it replaces."""
    attempt = next(e for e in run['prefixes'] if e['scenario'] == scenario)
    earlier = {**attempt, 'conversation_id': 'earlier-' + scenario, 'isolation_id': 'earlier-' + scenario,
               'turns': [{**turn, 'verdict': verdict} for turn in attempt['turns']],
               'status': 'failed' if verdict != 'pass' else 'passed'}
    return {**run, 'prefixes': [earlier, *run['prefixes']]}


def test_only_the_final_attempt_of_a_retried_scenario_counts():
    retried = _with_earlier_attempt(_run(1), 'B', 'fail')
    report = _summary([_run(0), retried, _run(2)])
    assert report['complete_repetitions'] == 3
    assert 'unaccepted_turn_failure' not in report['blocking_reasons']
    assert report['turn_pass_rates']['B:1'] == {'passed': 3, 'executed': 3}


def test_a_failing_final_attempt_is_not_hidden_by_an_earlier_clean_one():
    failing_last = _run(1, verdicts={'B:2': 'fail'})
    report = _summary([_run(0), _with_earlier_attempt(failing_last, 'B', 'pass'), _run(2)])
    assert 'unaccepted_turn_failure' in report['blocking_reasons']
    assert report['turn_pass_rates']['B:2'] == {'passed': 2, 'executed': 3}


@pytest.mark.parametrize('verdict', ['needs_review', 'incomplete', 'fail'])
def test_any_non_pass_verdict_without_a_named_failure_blocks_until_accepted(verdict):
    runs = [_run(0), _run(1, verdicts={'A:3': verdict}), _run(2)]
    assert 'unaccepted_turn_failure' in _reasons(runs)
    assert 'unaccepted_turn_failure' not in _reasons(runs, accepted_findings=[('A', 3)])


def test_every_run_id_is_retained_including_runs_that_did_not_count():
    partial = _run(1)
    partial['prefixes'] = partial['prefixes'][:-1]
    anonymous = {**_run(2), 'run_id': ''}
    summaries = _summary([_run(0), partial, anonymous])['runs']
    assert [s['run_id'] for s in summaries] == ['0', '1', '']
    assert [s['complete'] for s in summaries] == [True, False, False]


def test_an_open_coverage_gap_blocks_on_its_own_reason():
    gap = {'tool_coverage': [{'source': 'capability', 'state': 'gap', 'operation': 'x.y',
                              'reason': 'no turn reaches it'}]}
    reasons = _reasons([_run(i) for i in range(3)], coverage=gap)
    assert 'blocking_tool_implementation_gap' in reasons


def test_an_incomplete_run_blocks_even_when_every_recorded_turn_passed():
    incomplete = {**_run(1), 'incomplete_reason': 'aggregate_budget_exhausted'}
    report = _summary([_run(0), incomplete, _run(2)])
    assert report['complete_repetitions'] == 2
