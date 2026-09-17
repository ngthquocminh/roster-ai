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
