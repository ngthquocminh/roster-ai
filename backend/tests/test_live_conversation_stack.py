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


# --- the digests of the images the suite actually ran (Story 5.7 docs/evidence review) --

from evals.live_conversations.stack import (  # noqa: E402
    DATABASE_IMAGE, LIVE_IMAGES, ROOT, live_image_digests,
)

_ID = 'sha256:' + 'e' * 64


def _inspect(monkeypatch, *, stdout=_ID, returncode=0, error=None):
    seen = []

    def run(command, **_kwargs):
        seen.append(command)
        if error is not None:
            raise error
        return SimpleNamespace(returncode=returncode, stdout=stdout + '\n')

    monkeypatch.setattr(stack_module.subprocess, 'run', run)
    return seen


def test_the_recorded_digests_are_those_of_the_live_eval_images_not_the_local_build(monkeypatch):
    seen = _inspect(monkeypatch)
    digests = live_image_digests()
    assert digests == {'api': _ID, 'web': _ID, 'database': DATABASE_IMAGE}
    assert [command[3] for command in seen] == [LIVE_IMAGES['api'], LIVE_IMAGES['web']]
    assert all(image.endswith(':live-conversation-eval') for image in LIVE_IMAGES.values())


def test_the_stack_runs_the_very_images_whose_digests_are_recorded():
    env = _stack_environment(origin='http://localhost:18097', postgres_port=55497, model='m',
                             api_key='k', reasoning_effort='low', demonstration_enabled=False)
    assert (env['BACKEND_IMAGE'], env['WEB_IMAGE']) == (LIVE_IMAGES['api'], LIVE_IMAGES['web'])


@pytest.mark.parametrize('kwargs', [
    {'returncode': 1}, {'stdout': ''}, {'stdout': 'sha256:short'},
    {'stdout': 'shiftmind-backend:live-conversation-eval'},
    {'error': subprocess.TimeoutExpired('docker', 1)}, {'error': FileNotFoundError('docker')},
])
def test_an_image_whose_content_id_cannot_be_read_is_an_incomplete_run(monkeypatch, kwargs):
    _inspect(monkeypatch, **kwargs)
    with pytest.raises(IncompleteConversationRun, match='image_digest_unavailable'):
        live_image_digests()


def test_the_database_image_recorded_is_the_one_docker_compose_pins():
    assert f'image: {DATABASE_IMAGE}' in (ROOT / 'docker-compose.yml').read_text(encoding='utf-8')


# --- Story 5.9: trace export into the disposable stack ----------------------


def _captured_env(monkeypatch):
    seen = []
    monkeypatch.setattr(stack_module.subprocess, 'run',
                        lambda command, **kwargs: seen.append(kwargs.get('env')) or SimpleNamespace(returncode=0))
    monkeypatch.setattr(stack_module.httpx, 'get', lambda *_a, **_k: SimpleNamespace(status_code=200))
    return seen


def test_trace_export_reaches_the_stack_only_when_given(monkeypatch):
    monkeypatch.delenv('LOGFIRE_TOKEN', raising=False)
    monkeypatch.delenv('LOGFIRE_BASE_URL', raising=False)
    seen = _captured_env(monkeypatch)
    with _stack():
        pass
    assert all('LOGFIRE_TOKEN' not in env for env in seen)

    seen = _captured_env(monkeypatch)
    with _stack(trace_export={'LOGFIRE_TOKEN': 'CANARY-LOGFIRE-5-9', 'LOGFIRE_BASE_URL': None}):
        pass
    assert all(env['LOGFIRE_TOKEN'] == 'CANARY-LOGFIRE-5-9' for env in seen)
    assert all('LOGFIRE_BASE_URL' not in env for env in seen)


def test_the_logfire_token_never_enters_the_measured_configuration(monkeypatch):
    import json

    from evals.live_conversations.configuration import DEFAULT_OVERRIDE_FILE, measured_configuration

    monkeypatch.setenv('LOGFIRE_TOKEN', 'CANARY-LOGFIRE-5-9')
    report = measured_configuration(
        model='openrouter:openai/gpt-5.6-luna', judge_model='openrouter:google/gemini-2.5-flash',
        reasoning_effort='low', override_file=DEFAULT_OVERRIDE_FILE)
    assert 'CANARY-LOGFIRE-5-9' not in json.dumps(report)
    assert 'LOGFIRE' not in json.dumps(report)
