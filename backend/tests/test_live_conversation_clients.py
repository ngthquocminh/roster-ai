"""Protocol tests use HTTP doubles; these are not live acceptance evidence."""
import json

import httpx
import pytest

from evals.live_conversations.http_client import ApplicationConversation
from evals.live_conversations.judge import judge_turn, normalize_openrouter_model
from evals.live_conversations.protocol import ConversationBudget, IncompleteConversationRun
from tests.test_live_conversation_protocol import judgment, limits


def test_judge_sends_only_past_visible_data_and_requires_usable_usage():
    seen = []

    def handle(request):
        value = json.loads(request.content)
        seen.append(value)
        return httpx.Response(200, json={
            'id': 'generation-test', 'model': 'test-model',
            'choices': [{'message': {'content': judgment().model_dump_json(), 'reasoning': 'discard me'}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 80, 'cost': .001},
        })

    budget = ConversationBudget(limits())
    grade, usage = judge_turn(api_key='test-only', model='test-model',
                             transcript=[{'id': 'turn-1', 'user': 'Hello', 'reply': 'Hello'}],
                             obligation='Greet the user.', verified={'id': 'fixture-1'}, budget=budget,
                             client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert grade.passes(known_ids={'turn-1'})
    assert budget.spend_usd == .001 and budget.tokens == 180
    assert usage['generation_id'] == 'generation-test'
    assert 'reasoning' not in usage
    assert seen[0]['max_tokens'] == 2048
    assert seen[0]['provider']['require_parameters'] is True
    assert 'future' not in seen[0]['messages'][1]['content']


def test_direct_judge_normalizes_application_openrouter_model_reference():
    assert normalize_openrouter_model('openrouter:~deepseek/deepseek-flash-latest') == (
        '~deepseek/deepseek-flash-latest')
    assert normalize_openrouter_model('deepseek/deepseek-flash-latest') == (
        'deepseek/deepseek-flash-latest')


@pytest.mark.parametrize('reply', [
    {'choices': [{'message': {'content': '{}'}}], 'usage': {'prompt_tokens': 10, 'completion_tokens': 2, 'cost': .001}},
    {'choices': [{'message': {'content': judgment().model_dump_json()}}], 'usage': {}},
])
def test_judge_missing_fields_are_incomplete_and_never_leak_response(reply):
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(200, json=reply)))
    with pytest.raises(IncompleteConversationRun):
        judge_turn(api_key='test-only', model='test', transcript=[], obligation='Answer', verified={},
                   budget=ConversationBudget(limits()), client=client)


def test_judge_retries_one_malformed_structured_answer_and_charges_both_attempts():
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        content = '{}' if calls == 1 else judgment().model_dump_json()
        return httpx.Response(200, json={
            'id': f'generation-{calls}', 'model': 'test-model',
            'choices': [{'message': {'content': content}}],
            'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .001},
        })

    budget = ConversationBudget(limits())
    grade, usage = judge_turn(api_key='test', model='test', transcript=[], obligation='Answer',
        verified={}, budget=budget, client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert grade.verdict == 'pass'
    assert budget.requests == 2 and budget.spend_usd == .002
    assert [attempt['outcome'] for attempt in usage['attempts']] == ['malformed', 'accepted']


def test_judge_accepts_provider_decoded_strict_json_object():
    response = {
        'id': 'generation-object', 'model': 'test-model',
        'choices': [{'message': {'content': judgment().model_dump()}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .001},
    }
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response)))
    grade, usage = judge_turn(api_key='test', model='test', transcript=[], obligation='Answer',
        verified={}, budget=ConversationBudget(limits()), client=client)
    assert grade.verdict == 'pass'
    assert usage['attempts'][0]['outcome'] == 'accepted'


def test_application_client_uses_real_auth_csrf_and_new_conversations():
    posts = []

    def handle(request):
        path = request.url.path
        if path == '/api/v1/auth/login':
            return httpx.Response(302, headers={'location': 'http://app.test/oidc/authorize'})
        if path == '/oidc/authorize':
            return httpx.Response(302, headers={'location': 'http://app.test/api/v1/auth/callback'})
        if path == '/api/v1/auth/callback':
            return httpx.Response(302, headers={'set-cookie': '__Host-shiftmind_session=test; Secure', 'location': 'http://app.test/'})
        assert request.headers['Cookie'] == '__Host-shiftmind_session=test'
        if path == '/api/v1/auth/session':
            return httpx.Response(200, json={'csrf_token': 'test-csrf'})
        if path == '/api/v1/scenarios':
            return httpx.Response(200, json=[{'scenario_name': 'sample_tiny_input', 'scenario_id': 's', 'scenario_version_id': 'v'}])
        assert request.headers['X-CSRF-Token'] == 'test-csrf'
        if request.method == 'POST':
            posts.append(path)
        if path == '/api/v1/conversations':
            return httpx.Response(201, json={'id': f'conversation-{len(posts)}'})
        if path.endswith('/messages'):
            assert json.loads(request.content) == {'text': 'HI my name is Minh'}
            return httpx.Response(201, json={'agent_run_id': 'run-1'})
        if path.endswith('/execute'):
            return httpx.Response(200, json={'agent_run_status': 'agent_completed'})
        raise AssertionError(path)

    app = ApplicationConversation('http://app.test', client=httpx.Client(transport=httpx.MockTransport(handle)))
    app.login()
    first = app.create()['id']
    app.send('HI my name is Minh')
    second = app.create()['id']
    assert first != second
    assert posts == ['/api/v1/conversations', f'/api/v1/conversations/{first}/messages',
                     f'/api/v1/conversations/{first}/agent-runs/run-1/execute', '/api/v1/conversations']


def test_login_does_not_follow_an_unexpected_host():
    client = httpx.Client(transport=httpx.MockTransport(lambda request: httpx.Response(
        302, headers={'location': 'https://unrelated.invalid/callback'})))
    with pytest.raises(IncompleteConversationRun, match='unexpected_login_origin'):
        ApplicationConversation('http://app.test', client=client).login()


def test_transport_timeout_is_an_incomplete_application_observation():
    def timeout(_request):
        raise httpx.ReadTimeout('provider details must not enter evidence')

    app = ApplicationConversation('http://app.test',
        client=httpx.Client(transport=httpx.MockTransport(timeout)))
    with pytest.raises(IncompleteConversationRun, match='application_transport_unavailable'):
        app._request('GET', '/health')


def test_optimization_uses_latest_persisted_draft_version():
    commands = []

    def handle(request):
        path = request.url.path
        if path.endswith('/timeline'):
            return httpx.Response(200, json={'items': [
                {'activity_type': 'draft', 'proposal_id': 'old'},
                {'activity_type': 'draft', 'proposal_id': 'actual'},
            ], 'has_more': False})
        if path == '/api/v1/proposals/actual':
            return httpx.Response(200, json={'proposal_id': 'actual', 'state': 'active',
                                            'stale': False, 'resource_version': 3})
        assert path == '/api/v1/schedule-runs'
        assert request.headers['Idempotency-Key']
        commands.append(json.loads(request.content))
        return httpx.Response(200, json={'schedule_run_id': 'run', 'status': 'solver_queued'})

    app = ApplicationConversation('http://app.test', client=httpx.Client(transport=httpx.MockTransport(handle)))
    app.conversation = {'id': 'conversation'}
    assert app.run_optimization()['status'] == 'solver_queued'
    assert commands == [{'proposal_id': 'actual', 'expected_resource_version': 3}]


def test_no_draft_means_no_optimization_command():
    seen = []

    def handle(request):
        seen.append(request.method)
        return httpx.Response(200, json={'items': [], 'has_more': False})

    app = ApplicationConversation('http://app.test', client=httpx.Client(transport=httpx.MockTransport(handle)))
    app.conversation = {'id': 'conversation'}
    with pytest.raises(IncompleteConversationRun, match='required_draft_missing'):
        app.run_optimization()
    assert seen == ['GET']


def test_solver_polling_cannot_report_a_queued_run_as_complete(monkeypatch):
    monkeypatch.setattr('evals.live_conversations.http_client.sleep', lambda _: None)
    app = ApplicationConversation('http://app.test', client=httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={'status': 'solver_queued'}))))
    with pytest.raises(IncompleteConversationRun, match='solver_poll_budget_exhausted'):
        app.wait_for_run('run', max_polls=2)


@pytest.mark.parametrize('timeout', [float('nan'), float('inf')])
def test_solver_polling_rejects_non_finite_timeouts(timeout):
    app = ApplicationConversation('http://app.test')
    with pytest.raises(ValueError, match='bounded'):
        app.wait_for_run('run', timeout_seconds=timeout)
    app.close()


def test_approval_decision_uses_current_version_and_explicit_choice():
    commands = []

    def handle(request):
        if request.method == 'GET':
            return httpx.Response(200, json={'state': 'pending', 'resource_version': 4})
        commands.append(json.loads(request.content))
        assert request.url.path == '/api/v1/approvals/actual/decision'
        assert request.headers['Idempotency-Key']
        return httpx.Response(200, json={'state': 'rejected'})

    app = ApplicationConversation('http://app.test', client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert app.decide('actual', decision='reject')['state'] == 'rejected'
    assert commands == [{'decision': 'reject', 'expected_resource_version': 4}]
