"""Only the exception CLASS chain of a failed run is recovered from container logs."""
import json

from evals.live_conversations.telemetry import failure_exception_type

RUN = '11111111-2222-3333-4444-555555555555'


def _completed(run_id):
    return json.dumps({'event': 'agent.run.completed', 'correlation': {'agent_run_id': run_id}})


def _failure(*types):
    return json.dumps({'event': 'execute_agent_turn failed; finalizing run %s as terminal',
                       'level': 'ERROR', 'exception_type': list(types)})


def test_returns_the_class_chain_logged_before_this_runs_completion():
    log = '\n'.join([
        _completed('earlier'),
        _failure('UnexpectedModelBehavior', 'ModelRetry'),
        _completed(RUN),
    ])
    assert failure_exception_type(log, RUN) == ['UnexpectedModelBehavior', 'ModelRetry']


def test_a_failure_belonging_to_an_earlier_run_is_not_reattributed():
    log = '\n'.join([_failure('ValueError'), _completed('earlier'), _completed(RUN)])
    assert failure_exception_type(log, RUN) is None


# --- reading a run's records from a disposable container -----------------------

import subprocess
from types import SimpleNamespace

import pytest

from evals.live_conversations import telemetry as telemetry_module
from evals.live_conversations.protocol import IncompleteConversationRun
from evals.live_conversations.telemetry import ContainerTelemetry

CONTAINER = 'shiftmind-live-abc123-api-1'


def _record(event, run_id=RUN, **fields):
    return json.dumps({'event': event, 'correlation': {'agent_run_id': run_id}, **fields})


def _completed_record(**fields):
    body = {'usage': {'requests': 1}, 'estimated_cost_usd': .01, 'labels': {}, 'budget_outcome': 'ok'}
    return _record('agent.run.completed', **{**body, **fields})


def _read(monkeypatch, stdout='', stderr='', returncode=0, error=None):
    def run(*_args, **_kwargs):
        if error:
            raise error
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    monkeypatch.setattr(telemetry_module.subprocess, 'run', run)
    return ContainerTelemetry(CONTAINER).read_run(RUN)


@pytest.mark.parametrize('name', ['api', 'shiftmind-live-x', 'shiftmind-prod-x-api-1',
                                  'shiftmind-live-x-api-1; rm -rf /', 'shiftmind-live-X-api-1'])
def test_only_a_disposable_evaluation_container_can_be_read(name):
    with pytest.raises(ValueError, match='disposable'):
        ContainerTelemetry(name)


def test_a_docker_timeout_or_failure_makes_telemetry_unavailable_not_zero(monkeypatch):
    for kwargs in ({'error': subprocess.TimeoutExpired('docker', 1)}, {'returncode': 1}):
        with pytest.raises(IncompleteConversationRun, match='application_telemetry_unavailable'):
            _read(monkeypatch, **kwargs)


@pytest.mark.parametrize('stdout', ['', _completed_record() + '\n' + _completed_record()])
def test_a_run_needs_exactly_one_completion_record(monkeypatch, stdout):
    # Zero (logs truncated by --tail) or two (a replayed completion): either way the
    # usage cannot be attributed, so it is incomplete rather than free.
    with pytest.raises(IncompleteConversationRun, match='application_usage_or_cost_unavailable'):
        _read(monkeypatch, stdout=stdout)


def test_only_the_protocol_fields_survive_and_noise_lines_are_ignored(monkeypatch):
    stdout = '\n'.join(['not json', '[1, 2]', _record('agent.tool.call.completed', labels={'capability_name': 'x'}),
                         _completed_record(exception_message='a provider payload', prompt='secret'),
                         _completed_record()[:-3]])
    terminal, tools = _read(monkeypatch, stdout=stdout)
    assert 'exception_message' not in terminal and 'prompt' not in terminal
    assert terminal['usage'] == {'requests': 1} and len(tools) == 1


def test_records_of_other_runs_are_not_attributed_to_this_one(monkeypatch):
    stdout = _completed_record() + '\n' + _record('agent.run.completed', run_id='someone-else',
                                                   usage={'requests': 99}, estimated_cost_usd=9)
    terminal, _tools = _read(monkeypatch, stdout=stdout)
    assert terminal['usage'] == {'requests': 1}


def test_a_failed_turn_keeps_the_class_of_the_exception_that_caused_it(monkeypatch):
    stdout = '\n'.join([_failure('UnexpectedModelBehavior'),
                        _completed_record(labels={'failure_reason': 'invalid_output'})])
    terminal, _tools = _read(monkeypatch, stdout=stdout)
    assert terminal['failure_exception_type'] == ['UnexpectedModelBehavior']


def test_a_run_that_lost_its_usage_is_flagged_not_charged_as_free(monkeypatch):
    terminal, _tools = _read(monkeypatch, stdout=_completed_record(usage=None))
    assert terminal['usage_unavailable'] is True


def test_the_nearest_preceding_failure_wins_and_malformed_ones_are_ignored():
    log = '\n'.join([_failure('First'), _failure('Second'),
                     json.dumps({'event': 'execute_agent_turn failed', 'exception_type': 'not-a-list'}),
                     'garbage', _completed(RUN)])
    assert failure_exception_type(log, RUN) == ['Second']
