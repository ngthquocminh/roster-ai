"""The TypeSafe Jev live judge over an HTTP double; not live acceptance evidence."""
import json

import httpx
import pytest

from evals.live_conversations.jev_judge import (
    DEFAULT_JUDGE_MODEL, FAIL_P, PASS_P, TYPESAFE_JUDGE_ENDPOINT, USD_PER_INPUT_MTOK,
    is_typesafe_judge, judge_turn_jev, verdict_from,
)
from evals.live_conversations.protocol import (
    ConversationBudget, IncompleteConversationRun, turn_verdict,
)
from tests.test_live_conversation_protocol import limits

TRANSCRIPT = [{'id': 'turn-1', 'user': 'Hello', 'assistant': [{'text': 'Hello'}]}]


def _answer(p2, p1=None):
    p1 = (1 - p2) if p1 is None else p1
    return {'type': 'score', 'score': 2 * p2 + p1,
            'probabilities': {'0': round(1 - p2 - p1, 6), '1': p1, '2': p2}, 'confidence': .9}


def _body(p2_by_dimension, input_tokens=1000):
    return {'model': 'jev-1.13.0',
            'answers': {name: _answer(p2) for name, p2 in p2_by_dimension.items()},
            'usage': {'input_tokens': input_tokens, 'output_tokens': 20}}


ALL_MEET = {'relevance': .95, 'continuity': .9, 'completeness': .85,
            'clarification_refusal': .99}


def _judge(responses, *, not_applicable=frozenset(), seen=None, budget=None):
    replies = iter(responses)

    def handle(request):
        if seen is not None:
            seen.append((str(request.url), json.loads(request.content)))
        reply = next(replies)
        return reply() if callable(reply) else httpx.Response(200, json=reply)

    budget = budget or ConversationBudget(limits())
    return judge_turn_jev(
        api_key='test-only', model=DEFAULT_JUDGE_MODEL, transcript=TRANSCRIPT,
        obligation='Greet the user.', obligation_id='turn-1:obligation',
        verified={'id': 'turn-1:facts', 'effects_after_reply': [{'action': 'reload'}]},
        budget=budget, not_applicable=not_applicable,
        client=httpx.Client(transport=httpx.MockTransport(handle)))


def test_the_default_judge_is_a_pinned_typesafe_model():
    assert DEFAULT_JUDGE_MODEL == 'typesafe:jev-1.13.0'
    assert is_typesafe_judge(DEFAULT_JUDGE_MODEL)
    assert not is_typesafe_judge('openrouter:google/gemini-2.5-flash')


def test_one_typed_request_carries_past_data_and_no_output_schema():
    seen = []
    _judge([_body(ALL_MEET)], seen=seen)
    url, body = seen[0]
    assert url == TYPESAFE_JUDGE_ENDPOINT
    assert body['model'] == 'jev-1.13.0'  # the provider prefix is ours, not TypeSafe's
    assert set(body['state']) == {'grading_rules', 'transcript_so_far', 'current_obligation',
                                  'verified_facts'}
    assert body['state']['transcript_so_far'] == TRANSCRIPT
    assert body['state']['current_obligation'] == {'id': 'turn-1:obligation',
                                                   'text': 'Greet the user.'}
    assert set(body['questions']) == set(ALL_MEET)
    for question in body['questions'].values():
        assert question['type'] == 'score' and len(question['criteria']) == 3
    assert 'required_judgment_schema' not in json.dumps(body)


def test_a_not_applicable_dimension_is_not_asked_and_scores_null():
    seen = []
    applicable = {name: p for name, p in ALL_MEET.items() if name != 'clarification_refusal'}
    judgment, _ = _judge([_body(applicable)], seen=seen,
                         not_applicable=frozenset({'clarification_refusal'}))
    assert 'clarification_refusal' not in seen[0][1]['questions']
    assert judgment.clarification_refusal.score is None
    assert judgment.verdict == 'pass'
    assert turn_verdict(factual_failures=[], judgment=judgment, known_ids=set(),
                        not_applicable=frozenset({'clarification_refusal'})) == 'pass'


def test_every_dimension_meeting_passes_and_charges_input_tokens():
    budget = ConversationBudget(limits())
    judgment, usage = _judge([_body(ALL_MEET, input_tokens=5000)], budget=budget)
    assert judgment.verdict == 'pass'
    assert {judgment.relevance.score, judgment.completeness.score} == {2}
    assert judgment.relevance.reason is None
    assert judgment.unknown_citations(known_ids=set()) == []
    assert budget.spend_usd == pytest.approx(5000 * USD_PER_INPUT_MTOK / 1_000_000)
    assert budget.tokens == 5020 and budget.requests == 1
    assert usage['model'] == 'jev-1.13.0' and usage['attempts'][-1]['outcome'] == 'accepted'
    assert turn_verdict(factual_failures=[], judgment=judgment, known_ids=set()) == 'pass'


def test_one_clear_miss_fails_the_turn():
    judgment, _ = _judge([_body({**ALL_MEET, 'completeness': .1})])
    assert judgment.verdict == 'fail'
    assert judgment.completeness.score in (0, 1)
    assert turn_verdict(factual_failures=[], judgment=judgment, known_ids=set()) == 'fail'


def test_a_contested_dimension_is_uncertain_and_needs_review():
    judgment, _ = _judge([_body({**ALL_MEET, 'continuity': .5})])
    assert judgment.verdict == 'uncertain'
    assert turn_verdict(factual_failures=[], judgment=judgment, known_ids=set()) == 'needs_review'


def test_a_judge_pass_never_overrides_a_fact_failure():
    judgment, _ = _judge([_body(ALL_MEET)])
    assert turn_verdict(factual_failures=['x'], judgment=judgment, known_ids=set()) == 'fail'


@pytest.mark.parametrize('p_meets,expected', [
    ({'a': PASS_P, 'b': .99}, 'pass'),
    ({'a': PASS_P - .01, 'b': .99}, 'uncertain'),
    ({'a': FAIL_P, 'b': .99}, 'uncertain'),
    ({'a': FAIL_P - .01, 'b': .99}, 'fail'),
])
def test_the_verdict_thresholds_are_inclusive_at_pass_and_exclusive_at_fail(p_meets, expected):
    assert verdict_from(p_meets) == expected


def test_nothing_judged_is_never_a_pass():
    assert verdict_from({}) == 'uncertain'


def test_a_bogus_output_token_count_never_lowers_the_charged_total():
    body = _body(ALL_MEET, input_tokens=1000)
    body['usage']['output_tokens'] = -900
    budget = ConversationBudget(limits())
    _judge([body], budget=budget)
    assert budget.tokens == 1000


def test_an_even_split_is_scored_at_the_lower_level():
    body = _body(ALL_MEET)
    body['answers']['relevance'] = {'type': 'score', 'score': 1.5, 'confidence': .1,
                                    'probabilities': {'0': 0, '1': .5, '2': .5}}
    judgment, _ = _judge([body])
    assert judgment.relevance.score == 1


@pytest.mark.parametrize('status', [400, 413])
def test_a_request_the_service_rejects_is_final_without_retry(status):
    calls = []

    def reject():
        calls.append(status)
        return httpx.Response(status, json={'error': 'state too long'})

    with pytest.raises(IncompleteConversationRun, match=f'^judge_unavailable_http_{status}$'):
        _judge([reject, reject])
    assert len(calls) == 1


@pytest.mark.parametrize('first', [
    lambda: httpx.Response(429), lambda: httpx.Response(503),
    lambda: httpx.Response(200, json={'answers': {}}),  # usage missing
])
def test_a_transient_first_failure_is_retried_once(first):
    judgment, usage = _judge([first, _body(ALL_MEET)])
    assert judgment.verdict == 'pass'
    assert [attempt['outcome'] for attempt in usage['attempts']] == ['transport', 'accepted']


@pytest.mark.parametrize('mangle,category', [
    (lambda body: body['answers'].pop('continuity'), 'missing_answer'),
    (lambda body: body['answers']['relevance'].update(type='noul'), 'literal_error'),
    (lambda body: body['answers']['relevance']['probabilities'].pop('2'), 'value_error'),
    (lambda body: body['answers']['relevance']['probabilities'].update({'2': 1.5}), 'value_error'),
    # Each level in range, but together incoherent: P(2) and argmax would disagree.
    (lambda body: body['answers']['relevance']['probabilities'].update(
        {'0': .9, '1': 0, '2': .8}), 'value_error'),
])
def test_a_malformed_answer_retries_once_then_is_incomplete_and_both_are_charged(mangle, category):
    def bad():
        body = _body(ALL_MEET)
        mangle(body)
        return httpx.Response(200, json=body)

    budget = ConversationBudget(limits())
    with pytest.raises(IncompleteConversationRun, match=f'^judge_malformed_{category}_at_'):
        _judge([bad, bad], budget=budget)
    assert budget.requests == 2
