"""The suite's retry policy: which faults are retried, which stop the run at once.

Everything expensive (images, the isolated stack, the application, the paid
prefix itself) is replaced; only `suite.main`'s orchestration is under test."""
import json
from contextlib import contextmanager

import pytest

from evals.live_conversations import suite
from evals.live_conversations.cases import load_scenarios
from evals.live_conversations.protocol import IncompleteConversationRun

PASSED = {'status': 'passed', 'turns': []}
IMAGES = {'api': 'sha256:' + 'a' * 64, 'web': 'sha256:' + 'b' * 64, 'database': 'postgres:18'}


class Script:
    """What each step does on its Nth call: an exception instance to raise, or a value."""

    def __init__(self, *, login=(), baseline=(), execute=()):
        self.steps = {'login': list(login), 'baseline': list(baseline), 'execute': list(execute)}
        self.calls = {'login': 0, 'baseline': 0, 'execute': 0}

    def step(self, name):
        self.calls[name] += 1
        queued = self.steps[name]
        outcome = queued.pop(0) if queued else (PASSED if name == 'execute' else {})
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


@pytest.fixture
def run_suite(monkeypatch, tmp_path):
    import scripts.evidence_binding as binding

    monkeypatch.setattr(suite, 'dotenv_values', lambda _path: {
        'AGENT_RUNTIME_MODEL': 'openrouter:m', 'AGENT_RUNTIME_API_KEY': 'k',
        'LIVE_CONVERSATION_JUDGE_MODEL': 'j'})
    monkeypatch.setattr(binding, 'resolve_code_binding',
                        lambda *_args, **_kwargs: ({'git_commit': 'test-only'}, False))
    monkeypatch.setattr(suite, 'live_image_digests', lambda: IMAGES)

    def go(script, *extra):
        scenario = next(iter(load_scenarios()))

        class App:
            def __init__(self, _origin):
                pass

            def login(self):
                return script.step('login')

            def close(self):
                pass

        @contextmanager
        def stack(**_kwargs):
            yield {'origin': 'http://x', 'database_url': 'db', 'isolation_id': 'iso', 'container': 'c'}

        monkeypatch.setattr(suite, 'ApplicationConversation', App)
        monkeypatch.setattr(suite, 'isolated_stack', stack)
        monkeypatch.setattr(suite, 'prepare_initial_baseline',
                            lambda _app, **_kwargs: script.step('baseline'))
        monkeypatch.setattr(suite, 'ContainerTelemetry', lambda _container: None)
        monkeypatch.setattr(suite, 'execute_prefix', lambda **_kwargs: script.step('execute'))
        output = tmp_path / 'report.json'
        code = suite.main(['--scenario', scenario.id, '--endpoint', str(scenario.prefixes[0]),
                           '--output', str(output), '--skip-image-build', *extra])
        return code, json.loads(output.read_text(encoding='utf-8'))

    return go


def test_a_clean_execution_runs_once_and_passes(run_suite):
    script = Script()
    code, report = run_suite(script)
    assert code == 0 and script.calls == {'login': 1, 'baseline': 1, 'execute': 1}
    assert [p['attempt'] for p in report['prefixes']] == [1]


def test_a_login_fault_is_retried_on_a_fresh_stack_and_both_attempts_are_kept(run_suite):
    script = Script(login=[IncompleteConversationRun('authentication_failed')])
    code, report = run_suite(script)
    assert code == 0 and script.calls['login'] == 2 and script.calls['execute'] == 1
    assert [(p['attempt'], p.get('incomplete_reason')) for p in report['prefixes']] == [
        (1, 'authentication_failed'), (2, None)]


def test_a_fixture_seeding_fault_is_retried_like_any_other_infrastructure_fault(run_suite):
    script = Script(baseline=[IncompleteConversationRun('fixture_unavailable')])
    code, report = run_suite(script)
    assert code == 0 and script.calls['baseline'] == 2 and script.calls['execute'] == 1
    assert report['prefixes'][0]['incomplete_reason'] == 'fixture_unavailable'


def test_a_persistent_infrastructure_fault_ends_the_run_incomplete_after_the_retries(run_suite):
    fault = IncompleteConversationRun('authentication_failed')
    script = Script(login=[fault, fault, fault])
    code, report = run_suite(script, '--execution-retries', '2')
    assert code == 2 and script.calls['login'] == 3 and script.calls['execute'] == 0
    assert report['incomplete_reason'].endswith('authentication_failed')


@pytest.mark.parametrize('reason', ['aggregate_budget_exhausted', 'case_budget_exhausted'])
def test_an_exhausted_shared_budget_stops_at_once_instead_of_burning_retries(run_suite, reason):
    # A fresh stack cannot refill a process-wide budget; retrying only wastes setup time.
    script = Script(execute=[{'status': 'incomplete', 'turns': [], 'incomplete_reason': reason}])
    code, report = run_suite(script, '--execution-retries', '2')
    assert code == 2 and script.calls['execute'] == 1 and script.calls['login'] == 1
    assert report['incomplete_reason'].endswith(reason)


def test_a_failed_scenario_is_a_result_not_a_retry(run_suite):
    script = Script(execute=[{'status': 'failed', 'turns': []}])
    code, report = run_suite(script)
    assert code == 1 and script.calls['execute'] == 1
    assert len(report['prefixes']) == 1


def test_a_run_that_recovered_on_retry_exits_zero_but_a_last_attempt_that_failed_does_not(run_suite):
    recovered = Script(login=[IncompleteConversationRun('authentication_failed')])
    assert run_suite(recovered)[0] == 0
    failed_last = Script(login=[IncompleteConversationRun('authentication_failed')],
                         execute=[{'status': 'failed', 'turns': []}])
    assert run_suite(failed_last)[0] == 1


# --- what the report says it ran (Story 5.7 docs/evidence review) -----------------

def test_the_report_records_the_images_and_the_configuration_it_ran(run_suite):
    _code, report = run_suite(Script())
    assert report['images'] == IMAGES
    configuration = report['configuration']
    assert configuration['agent']['model'] == 'openrouter:m' and configuration['judge']['model'] == 'j'
    assert configuration['reasoning_effort'] == 'low'
    assert configuration['override_file'] == 'backend/evals/live_conversations/compose.override.yml'
    assert 'k' not in {value for value in configuration.values() if isinstance(value, str)}


def test_images_that_cannot_be_read_end_the_run_before_any_execution(run_suite, monkeypatch):
    def unreadable():
        raise IncompleteConversationRun('image_digest_unavailable')

    monkeypatch.setattr(suite, 'live_image_digests', unreadable)
    script = Script()
    code, report = run_suite(script)
    assert code == 2 and script.calls == {'login': 0, 'baseline': 0, 'execute': 0}
    assert report['incomplete_reason'] == 'image_digest_unavailable' and report['images'] is None


def test_a_report_from_a_different_configuration_cannot_be_resumed(run_suite, tmp_path):
    earlier = tmp_path / 'earlier.json'
    earlier.write_text(json.dumps({'code': {'git_commit': 'test-only'}, 'images': IMAGES,
                                   'configuration': {'reasoning_effort': 'high'},
                                   'prefixes': []}), encoding='utf-8')
    with pytest.raises(SystemExit, match='different configuration'):
        run_suite(Script(), '--resume', str(earlier))


def test_a_report_measured_on_different_images_cannot_be_resumed(run_suite, monkeypatch, tmp_path):
    _code, first = run_suite(Script())
    earlier = tmp_path / 'earlier.json'
    earlier.write_text(json.dumps(first), encoding='utf-8')
    monkeypatch.setattr(suite, 'live_image_digests',
                        lambda: {**IMAGES, 'api': 'sha256:' + 'c' * 64})
    with pytest.raises(SystemExit, match='images now built differ'):
        run_suite(Script(), '--resume', str(earlier))
    monkeypatch.setattr(suite, 'live_image_digests', lambda: IMAGES)
    assert run_suite(Script(), '--resume', str(earlier))[0] == 0
