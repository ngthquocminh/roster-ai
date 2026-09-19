from evals.live_conversations.stack import _stack_environment


def test_isolated_stack_uses_backend_demonstration_setting_name():
    env = _stack_environment(origin='http://localhost:18097', postgres_port=55497,
        model='test', api_key='secret', reasoning_effort='low', demonstration_enabled=True)
    assert env['DEMONSTRATION_ENABLED'] == 'true'
    assert 'SHIFTMIND_DEMONSTRATION_ENABLED' not in env


# --- teardown, timeouts and readiness (Story 5.7 eval-harness review patches) --

import subprocess
from types import SimpleNamespace

import httpx
import pytest

from evals.live_conversations import stack as stack_module
from evals.live_conversations.protocol import IncompleteConversationRun
from evals.live_conversations.stack import build_live_images, isolated_stack


def _docker(monkeypatch, *, up=0, down=0, health=200):
    """Replace docker and the readiness probe; returns the commands that were run."""
    commands = []

    def run(command, **_kwargs):
        commands.append(command)
        verb = next(v for v in ('build', 'up', 'down') if v in command)
        outcome = {'build': 0, 'up': up, 'down': down}[verb]
        if isinstance(outcome, Exception):
            raise outcome
        return SimpleNamespace(returncode=outcome)

    monkeypatch.setattr(stack_module.subprocess, 'run', run)
    monkeypatch.setattr(stack_module.httpx, 'get', lambda *_a, **_k: SimpleNamespace(status_code=health))
    monkeypatch.setattr(stack_module, 'sleep', lambda _seconds: None)
    return commands


def _stack(**extra):
    return isolated_stack(model='m', api_key='k', override_file='override.yml', **extra)


def test_a_slow_image_build_is_an_incomplete_run_not_a_hang(monkeypatch):
    _docker(monkeypatch)
    monkeypatch.setattr(stack_module.subprocess, 'run',
                        lambda *_a, **_k: (_ for _ in ()).throw(subprocess.TimeoutExpired('docker', 1)))
    with pytest.raises(IncompleteConversationRun, match='isolated_stack_build_failed'):
        build_live_images(model='m', api_key='k', override_file='override.yml')


def test_a_failed_image_build_is_an_incomplete_run(monkeypatch):
    monkeypatch.setattr(stack_module.subprocess, 'run', lambda *_a, **_k: SimpleNamespace(returncode=1))
    with pytest.raises(IncompleteConversationRun, match='isolated_stack_build_failed'):
        build_live_images(model='m', api_key='k', override_file='override.yml')


@pytest.mark.parametrize('up', [1, subprocess.TimeoutExpired('docker', 1)])
def test_a_stack_that_will_not_start_is_incomplete_and_is_still_torn_down(monkeypatch, up):
    commands = _docker(monkeypatch, up=up)
    with pytest.raises(IncompleteConversationRun, match='isolated_stack_start_failed'):
        with _stack():
            pass
    assert any('down' in command and '--volumes' in command for command in commands)


def test_a_stack_that_never_answers_its_health_check_is_not_ready(monkeypatch):
    _docker(monkeypatch, health=503)
    clock = iter(range(0, 10_000, 30))
    monkeypatch.setattr(stack_module, 'monotonic', lambda: next(clock))
    with pytest.raises(IncompleteConversationRun, match='isolated_stack_not_ready'):
        with _stack():
            pass


def test_teardown_is_scoped_to_this_prefixs_own_generated_project(monkeypatch):
    commands = _docker(monkeypatch)
    with _stack() as live:
        assert live['container'] == live['isolation_id'] + '-api-1'
    down = next(command for command in commands if 'down' in command)
    assert down[down.index('-p') + 1] == live['isolation_id']
    assert live['isolation_id'].startswith('shiftmind-live-')


@pytest.mark.parametrize('down', [1, subprocess.TimeoutExpired('docker', 1)])
def test_a_teardown_failure_is_reported_when_nothing_else_is_failing(monkeypatch, down):
    _docker(monkeypatch, down=down)
    with pytest.raises(IncompleteConversationRun, match='isolated_stack_cleanup_failed'):
        with _stack():
            pass


def test_a_teardown_failure_never_hides_the_real_root_cause(monkeypatch):
    _docker(monkeypatch, down=1)
    with pytest.raises(RuntimeError, match='the real problem'):
        with _stack():
            raise RuntimeError('the real problem')
