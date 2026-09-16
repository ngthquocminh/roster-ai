from evals.live_conversations.cases import load_scenarios, prefix_executions
from evals.live_conversations.reporting import summarize_runs


def test_missing_runs_and_browser_cannot_become_eligible():
    report = summarize_runs([], coverage={}, observation_ids=set(), version_bindings={}, browser={})
    assert report['readiness'] == 'blocked'
    assert report['live_conversation_journeys'] == 'blocked'
    assert report['required_prefixes_per_run'] == 40
    assert report['required_user_turns_per_run'] == 273


def test_incomplete_prefix_resets_consecutive_run_streak():
    binding = {'code': {'git_commit': 'test-only', 'working_tree_dirty': False}}
    prefixes = [{'scenario': case.id, 'endpoint': endpoint,
                 'conversation_id': case.id + str(endpoint), 'isolation_id': case.id + str(endpoint),
                 'status': 'passed', 'turns': [{'user': t.user, 'verdict': 'pass'} for t in turns]}
                for case, endpoint, turns in prefix_executions(load_scenarios())]
    full = {'run_id': 'test-only', 'version_bindings': binding, 'prefixes': prefixes}
    partial = {**full, 'prefixes': prefixes[:-1]}
    def unique(run, number):
        return {**run, 'run_id': str(number), 'prefixes': [
            {**p, 'conversation_id': str(number) + p['conversation_id'],
             'isolation_id': str(number) + p['isolation_id']} for p in run['prefixes']]}
    report = summarize_runs([unique(run, i) for i, run in enumerate([full, full, partial, full])], coverage={}, observation_ids=set(),
                             version_bindings=binding, browser={})
    assert report['consecutive_passes'] == 1
    assert report['runs'][2]['complete'] is False
    assert report['readiness'] == 'blocked'


def test_reused_conversation_cannot_count_as_independent_prefixes():
    binding = {'code': {'git_commit': 'test-only', 'working_tree_dirty': False}}
    prefixes = [{'scenario': case.id, 'endpoint': endpoint, 'conversation_id': 'reused',
                 'isolation_id': case.id + str(endpoint), 'status': 'passed',
                 'turns': [{'user': t.user, 'verdict': 'pass'} for t in turns]}
                for case, endpoint, turns in prefix_executions(load_scenarios())]
    report = summarize_runs([{'version_bindings': binding, 'prefixes': prefixes}], coverage={},
                             observation_ids=set(), version_bindings=binding, browser={})
    assert report['consecutive_passes'] == 0
