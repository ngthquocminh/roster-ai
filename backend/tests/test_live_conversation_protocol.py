from dataclasses import replace

import pytest
from pydantic import ValidationError

from evals.live_conversations.protocol import (
    ConversationBudget, ConversationJudgment, IncompleteConversationRun, turn_verdict,
)
from evals.report import LiveSuiteBudgetV1


def limits():
    return LiveSuiteBudgetV1(case_limit=40, request_limit=100, tool_call_limit=100,
                            token_limit=10000, elapsed_seconds_limit=600, spend_usd_limit=7)


def judgment(**updates):
    data = {name: {'score': 2, 'evidence_ids': ['turn-1'], 'reason': 'Supported by the current turn.'}
            for name in ('relevance', 'continuity', 'completeness', 'clarification_refusal')}
    data.update(verdict='pass', **updates)
    return ConversationJudgment.model_validate(data)


def test_budget_reserves_next_call_and_counts_preceding_story_spend():
    budget = ConversationBudget(limits(), prior_spend_usd=1)
    budget.charge(requests=3, tool_calls=1, tokens=500, cost_usd=5.9)
    with pytest.raises(IncompleteConversationRun, match='budget_exhausted'):
        budget.admit(reserve_usd=.2)
    budget.admit(reserve_usd=.05)


@pytest.mark.parametrize('value', [True, '1', None])
def test_prior_spend_must_be_a_real_number(value):
    with pytest.raises(ValueError, match='prior spend'):
        ConversationBudget(limits(), prior_spend_usd=value)


@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1, None, True, '0'])
def test_bad_cost_cannot_count_as_free(value):
    with pytest.raises(IncompleteConversationRun, match='cost_unavailable'):
        ConversationBudget(limits()).charge(requests=1, tool_calls=0, tokens=10, cost_usd=value)


def test_missing_usage_is_incomplete():
    with pytest.raises(IncompleteConversationRun, match='usage_unavailable'):
        ConversationBudget(limits()).charge(requests=None, tool_calls=0, tokens=10, cost_usd=0)


@pytest.mark.parametrize('usage', [
    dict(requests=101, tool_calls=0, tokens=0, cost_usd=0),
    dict(requests=1, tool_calls=101, tokens=0, cost_usd=0),
    dict(requests=1, tool_calls=0, tokens=10001, cost_usd=0),
    dict(requests=1, tool_calls=0, tokens=0, cost_usd=7.01),
])
def test_final_call_exceeding_any_ceiling_is_incomplete(usage):
    budget = ConversationBudget(limits())
    with pytest.raises(IncompleteConversationRun, match='budget_exhausted'):
        budget.charge(**usage)
    assert budget.spend_usd == usage['cost_usd']


def test_elapsed_ceiling_applies_even_to_last_call():
    budget = ConversationBudget(limits(), started=0)
    with pytest.raises(IncompleteConversationRun, match='budget_exhausted'):
        budget.charge(requests=1, tool_calls=0, tokens=1, cost_usd=.01)


@pytest.mark.parametrize('requests,tokens', [(-1, 0), (1, -1), (True, 0), (1, 1.5)])
def test_reservations_cannot_reduce_usage(requests, tokens):
    with pytest.raises(ValueError):
        ConversationBudget(limits()).admit(reserve_usd=.01, requests=requests, tokens=tokens)


def test_a_judge_pass_cannot_override_a_wrong_fact():
    assert turn_verdict(factual_failures=['wrong_worker_count'], judgment=judgment(),
                        known_ids={'turn-1'}) == 'fail'


def test_partial_dimension_cannot_be_hidden_in_an_average():
    partial = judgment(completeness={'score': 1, 'evidence_ids': ['turn-1'], 'reason': 'Missing result.'})
    assert not partial.passes(known_ids={'turn-1'})


def test_judge_cannot_invent_evidence_or_exempt_dimensions():
    assert not judgment().passes(known_ids={'different-turn'})
    exempt = judgment(continuity={'score': None, 'evidence_ids': ['turn-1'], 'reason': 'First turn.'})
    assert not exempt.passes(known_ids={'turn-1'})
    assert exempt.passes(known_ids={'turn-1'}, not_applicable=frozenset({'continuity'}))
    empty_exempt = judgment(continuity={
        'score': None, 'evidence_ids': [], 'reason': 'Not applicable.'})
    assert empty_exempt.passes(known_ids={'turn-1'},
                              not_applicable=frozenset({'continuity'}))
    empty_applicable = judgment(continuity={
        'score': 2, 'evidence_ids': [], 'reason': 'Missing citation.'})
    assert not empty_applicable.passes(known_ids={'turn-1'})


def test_missing_or_uncertain_judgments_are_not_automatic_passes():
    assert turn_verdict(factual_failures=[], judgment=None, known_ids={'turn-1'}) == 'incomplete'
    uncertain = judgment().model_copy(update={'verdict': 'uncertain'})
    assert turn_verdict(factual_failures=[], judgment=uncertain, known_ids={'turn-1'}) == 'needs_review'


def test_judgment_rejects_malformed_score_and_extra_provider_content():
    data = judgment().model_dump()
    data['relevance']['score'] = '2'
    with pytest.raises(ValidationError):
        ConversationJudgment.model_validate(data)
    data = judgment().model_dump()
    data['reasoning'] = 'must not enter evidence'
    with pytest.raises(ValidationError):
        ConversationJudgment.model_validate(data)
