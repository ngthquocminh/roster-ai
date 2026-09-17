import json

import httpx
import pytest

from agent.runtime import AgentRuntimeConfig, PydanticAIAgentRuntime
from application.contracts.agent_runtime import AgentTurnRequestV1
from settings import InvalidFlagError, default_settings


def test_invalid_reasoning_effort_fails_configuration(monkeypatch):
    monkeypatch.setenv('AGENT_RUNTIME_REASONING_EFFORT', 'unbounded')
    with pytest.raises(InvalidFlagError, match='AGENT_RUNTIME_REASONING_EFFORT'):
        default_settings()


def test_explicit_reasoning_control_reaches_openrouter_request(monkeypatch):
    from pydantic_ai.providers.openrouter import OpenRouterProvider
    requests = []

    def handle(request):
        requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            'id': 'test-completion', 'object': 'chat.completion', 'created': 1, 'model': 'test',
            'provider': 'Test',  # real OpenRouter responses always name the upstream provider
            'choices': [{'index': 0, 'message': {'role': 'assistant', 'content': 'Hello'}, 'finish_reason': 'stop'}],
            'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'total_tokens': 12},
        })

    client = httpx.AsyncClient(transport=httpx.MockTransport(handle))
    monkeypatch.setattr('pydantic_ai.providers.openrouter.OpenRouterProvider',
                        lambda **kwargs: OpenRouterProvider(api_key='test', http_client=client))
    runtime = PydanticAIAgentRuntime(config=AgentRuntimeConfig(
        model='openrouter:deepseek/test', api_key='test', reasoning_effort='low'))
    # Other test modules set `models.ALLOW_MODEL_REQUESTS = False` at import
    # scope (a process-wide, never-reset flag) to keep themselves off the
    # network. This test's request never leaves the process (MockTransport),
    # so it needs the flag back on for just this call.
    from pydantic_ai import models
    with models.override_allow_model_requests(True):
        assert runtime.run_turn(AgentTurnRequestV1(prompt='Hello')).output_text == 'Hello'
    assert requests[0]['reasoning'] == {'effort': 'low'}
