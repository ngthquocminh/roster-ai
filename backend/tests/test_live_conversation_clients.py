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
    assert seen[0]['max_tokens'] == 3072  # raised after malformed (truncated) judgments
    assert seen[0]['provider']['require_parameters'] is True
    assert seen[0]['response_format'] == {'type': 'json_object'}
    judge_input = json.loads(seen[0]['messages'][1]['content'])
    assert 'required_judgment_schema' in judge_input
    assert judge_input['current_obligation'] == {'id': 'obligation', 'text': 'Greet the user.'}
    # The judge sends exactly what it was given plus the fixed rubric fields, so a
    # caller that slices the transcript to past turns cannot leak more through here.
    assert judge_input['transcript_so_far'] == [{'id': 'turn-1', 'user': 'Hello', 'reply': 'Hello'}]
    assert set(judge_input) == {'transcript_so_far', 'current_obligation',
                                'verified_facts_and_effects', 'not_applicable',
                                'required_judgment_schema'}
    assert 'score completeness 2' in seen[0]['messages'][0]['content']
    assert 'alternatives with "or"' in seen[0]['messages'][0]['content']


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
    with pytest.raises(IncompleteConversationRun, match='^judge_') as raised:
        judge_turn(api_key='test-only', model='test', transcript=[], obligation='Answer', verified={},
                   budget=ConversationBudget(limits()), client=client)
    # The reason names a failure class, never the provider's body.
    assert 'choices' not in str(raised.value) and 'verdict' not in str(raised.value)


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


_USAGE = {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .001}


def _judged_body(generation, content=None):
    return {'id': generation, 'model': 'test-model', 'usage': _USAGE,
            'choices': [{'message': {'content': content or judgment().model_dump_json()}}]}


# first-attempt failure -> (reply, outcome recorded, spend the failed attempt was charged)
_FIRST_ATTEMPT_FAILURES = {
    'prose_instead_of_json': (
        lambda: httpx.Response(200, json=_judged_body('g1', 'Sure! Here is my verdict: pass')),
        'malformed', .001),
    'no_choices': (
        lambda: httpx.Response(200, json={**_judged_body('g1'), 'choices': []}), 'malformed', .001),
    'non_200_status': (lambda: httpx.Response(503, json={}), 'transport', 0),
    'missing_usage': (
        lambda: httpx.Response(200, json={**_judged_body('g1'), 'usage': {}}), 'transport', 0),
}


@pytest.mark.parametrize('failure', sorted(_FIRST_ATTEMPT_FAILURES))
def test_judge_retries_every_transient_first_attempt_failure_once(failure):
    first, outcome, first_spend = _FIRST_ATTEMPT_FAILURES[failure]
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return first() if calls == 1 else httpx.Response(200, json=_judged_body('g2'))

    budget = ConversationBudget(limits())
    grade, usage = judge_turn(api_key='test', model='test', transcript=[], obligation='Answer',
        verified={}, budget=budget, client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert calls == 2 and grade.verdict == 'pass'
    assert [a['outcome'] for a in usage['attempts']] == [outcome, 'accepted']
    assert budget.spend_usd == pytest.approx(first_spend + .001)


def test_judge_gives_up_after_a_second_non_json_answer_and_charges_both_calls():
    calls = 0

    def handle(request):
        nonlocal calls
        calls += 1
        return httpx.Response(200, json=_judged_body(f'g{calls}', 'not json at all'))

    budget = ConversationBudget(limits())
    with pytest.raises(IncompleteConversationRun, match='judge_malformed_JSONDecodeError'):
        judge_turn(api_key='test', model='test', transcript=[], obligation='Answer', verified={},
                   budget=budget, client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert calls == 2 and budget.spend_usd == pytest.approx(.002)


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


def test_judge_accepts_single_openai_text_content_block():
    response = {
        'id': 'generation-block', 'model': 'test-model',
        'choices': [{'message': {'content': [
            {'type': 'text', 'text': judgment().model_dump_json()}]}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .001},
    }
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response)))
    grade, _ = judge_turn(api_key='test', model='test', transcript=[], obligation='Answer',
        verified={}, budget=ConversationBudget(limits()), client=client)
    assert grade.verdict == 'pass'


def test_judge_accepts_one_double_encoded_json_layer():
    response = {
        'id': 'generation-encoded', 'model': 'test-model',
        'choices': [{'message': {'content': json.dumps(judgment().model_dump_json())}}],
        'usage': {'prompt_tokens': 100, 'completion_tokens': 20, 'cost': .001},
    }
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json=response)))
    grade, _ = judge_turn(api_key='test', model='test', transcript=[], obligation='Answer',
        verified={}, budget=ConversationBudget(limits()), client=client)
    assert grade.verdict == 'pass'


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
    app.send('HI my name is Minh')
    # The proof of "a NEW conversation" is the client's own requests, not the ids the
    # double hands back: create() posted again, and the next message went to that one.
    assert posts == ['/api/v1/conversations', f'/api/v1/conversations/{first}/messages',
                     f'/api/v1/conversations/{first}/agent-runs/run-1/execute', '/api/v1/conversations',
                     f'/api/v1/conversations/{second}/messages',
                     f'/api/v1/conversations/{second}/agent-runs/run-1/execute']
    assert first != second


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


def test_an_execute_404_is_retried_once_and_recorded(monkeypatch):
    """The 404 seen twice in ~20 live executions: execute could not find a run
    the immediately preceding 201 had just created."""
    from evals.live_conversations.http_client import ApplicationConversation
    from evals.live_conversations.protocol import IncompleteConversationRun

    calls = []

    class Client:
        def request(self, method, url, **kwargs):
            calls.append((method, url))
            if url.endswith('/messages'):
                return httpx.Response(201, json={'agent_run_id': 'run-1', 'activity': {},
                                                 'resource_version': 2, 'sequence': '1',
                                                 'agent_run_status': 'agent_queued'})
            if len([c for c in calls if c[1].endswith('/execute')]) == 1:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={'activity': {'activity_type': 'agent_response'},
                                             'agent_run_status': 'agent_completed'})

    app = ApplicationConversation.__new__(ApplicationConversation)
    app.origin, app.client, app.headers = 'http://x', Client(), {}
    app.conversation = {'id': 'c-1'}
    monkeypatch.setattr('evals.live_conversations.http_client.sleep', lambda _seconds: None)

    accepted, executed = app.send('hello')
    assert accepted['execute_retried_after_404'] is True
    assert executed['agent_run_status'] == 'agent_completed'
    assert len([c for c in calls if c[1].endswith('/execute')]) == 2


def test_an_execute_404_that_persists_is_reported_as_still_missing(monkeypatch):
    from evals.live_conversations.http_client import ApplicationConversation
    from evals.live_conversations.protocol import IncompleteConversationRun

    class Client:
        def request(self, method, url, **kwargs):
            if url.endswith('/messages'):
                return httpx.Response(201, json={'agent_run_id': 'run-1'})
            return httpx.Response(404, json={})

    app = ApplicationConversation.__new__(ApplicationConversation)
    app.origin, app.client, app.headers = 'http://x', Client(), {}
    app.conversation = {'id': 'c-1'}
    monkeypatch.setattr('evals.live_conversations.http_client.sleep', lambda _seconds: None)

    with pytest.raises(IncompleteConversationRun, match='still_missing_after_retry'):
        app.send('hello')


def test_a_run_that_is_not_visible_yet_is_polled_again_not_abandoned(monkeypatch):
    """live-suite-evidence-final died on GET /schedule-runs/* 404 for a run its
    own POST had just created."""
    from evals.live_conversations.http_client import ApplicationConversation

    calls = []

    class Client:
        def request(self, method, url, **kwargs):
            calls.append(url)
            if url.endswith('/result'):
                return httpx.Response(200, json={'run': {'status': 'solver_completed'}})
            if len(calls) == 1:
                return httpx.Response(404, json={})
            return httpx.Response(200, json={'status': 'solver_completed'})

    app = ApplicationConversation.__new__(ApplicationConversation)
    app.origin, app.client, app.headers = 'http://x', Client(), {}
    monkeypatch.setattr('evals.live_conversations.http_client.sleep', lambda _s: None)

    assert app.wait_for_run('run-1')['run']['status'] == 'solver_completed'
    assert app.run_not_visible_polls == 1


def test_a_run_that_never_becomes_visible_still_exhausts_its_budget(monkeypatch):
    from evals.live_conversations.http_client import ApplicationConversation
    from evals.live_conversations.protocol import IncompleteConversationRun

    class Client:
        def request(self, method, url, **kwargs):
            return httpx.Response(404, json={})

    app = ApplicationConversation.__new__(ApplicationConversation)
    app.origin, app.client, app.headers = 'http://x', Client(), {}
    monkeypatch.setattr('evals.live_conversations.http_client.sleep', lambda _s: None)

    with pytest.raises(IncompleteConversationRun, match='solver_poll_budget_exhausted'):
        app.wait_for_run('run-1', max_polls=3)


def _client_over(handler):
    app = ApplicationConversation.__new__(ApplicationConversation)
    app.origin, app.headers = 'http://x', {}
    app.client = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=False)
    return app


def test_a_body_that_is_not_json_is_an_undecodable_response_not_a_crash():
    app = _client_over(lambda request: httpx.Response(200, content=b'<html>gateway error</html>'))
    with pytest.raises(IncompleteConversationRun, match='^application_response_undecodable$'):
        app._request('GET', '/api/v1/anything')


def test_an_unexpected_status_names_the_route_with_ids_masked_and_no_body():
    app = _client_over(lambda request: httpx.Response(500, text='secret provider payload'))
    with pytest.raises(IncompleteConversationRun) as raised:
        app._request('GET', '/api/v1/schedule-runs/123e4567-e89b-12d3-a456-426614174000?x=1')
    assert str(raised.value) == 'application_http_500_GET_/api/v1/schedule-runs/*'


def test_a_transport_failure_is_reported_as_unavailable():
    def refuse(request):
        raise httpx.ConnectError('refused')

    with pytest.raises(IncompleteConversationRun, match='^application_transport_unavailable$'):
        _client_over(refuse)._request('GET', '/api/v1/anything')


def test_login_needs_a_redirect_at_every_hop():
    app = _client_over(lambda request: httpx.Response(200, json={}))
    with pytest.raises(IncompleteConversationRun, match='^authentication_failed$'):
        app.login()


def test_a_redirect_with_no_location_cannot_authenticate():
    app = _client_over(lambda request: httpx.Response(302))
    with pytest.raises(IncompleteConversationRun, match='^authentication_failed$'):
        app.login()


def test_login_gives_up_after_three_redirects_that_never_set_a_session():
    hops = []

    def loop(request):
        hops.append(str(request.url))
        return httpx.Response(302, headers={'location': 'http://x/api/v1/auth/again'})

    with pytest.raises(IncompleteConversationRun, match='^authentication_failed$'):
        _client_over(loop).login()
    assert len(hops) == 3


def test_login_stops_when_a_later_hop_leaves_the_application_origin():
    def leave(request):
        return httpx.Response(302, headers={'location': 'http://evil.example/steal'})

    with pytest.raises(IncompleteConversationRun, match='^unexpected_login_origin$'):
        _client_over(leave).login()


def test_login_keeps_only_the_session_cookie_pair(monkeypatch):
    app = _client_over(lambda request: httpx.Response(302, headers={
        'set-cookie': '__Host-shiftmind_session=abc; Path=/; HttpOnly; Secure'}))
    monkeypatch.setattr(app, '_request', lambda method, path, **kw: {'csrf_token': 'csrf-1'})
    app.login()
    assert app.headers['Cookie'] == '__Host-shiftmind_session=abc'
    assert app.headers['X-CSRF-Token'] == 'csrf-1' and app.headers['Origin'] == 'http://x'
