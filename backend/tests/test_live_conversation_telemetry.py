"""Only the exception CLASS of a failed run is recovered from container logs."""
from evals.live_conversations.telemetry import failure_exception_type

RUN = '11111111-2222-3333-4444-555555555555'


def test_returns_the_final_exception_class_without_its_message():
    log = '\n'.join([
        '{"event": "agent.tool.call.completed"}',
        f'ERROR execute_agent_turn failed; finalizing run {RUN} as terminal',
        'Traceback (most recent call last):',
        '  File "/app/agent/runtime.py", line 1, in run_turn',
        'pydantic_ai.exceptions.ModelRetry: rewrite the prose segment "10 workers"',
        '',
        'The above exception was the direct cause of the following exception:',
        'pydantic_ai.exceptions.UnexpectedModelBehavior: Exceeded maximum retries (2) for output validation',
        '{"event": "agent.run.completed"}',
    ])
    assert failure_exception_type(log, RUN) == 'pydantic_ai.exceptions.UnexpectedModelBehavior'


def test_other_runs_and_missing_markers_yield_nothing():
    log = 'ERROR execute_agent_turn failed; finalizing run other as terminal\nValueError: x'
    assert failure_exception_type(log, RUN) is None
