from evals.live_conversations.stack import _stack_environment


def test_isolated_stack_uses_backend_demonstration_setting_name():
    env = _stack_environment(origin='http://localhost:18097', postgres_port=55497,
        model='test', api_key='secret', reasoning_effort='low', demonstration_enabled=True)
    assert env['DEMONSTRATION_ENABLED'] == 'true'
    assert 'SHIFTMIND_DEMONSTRATION_ENABLED' not in env
