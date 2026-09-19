from dataclasses import replace
from time import monotonic

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
    # Relative to now, not to the clock's epoch: `started=0` only exceeded the
    # limit on a host whose monotonic clock had already passed 600 s.
    budget = ConversationBudget(limits(), started=monotonic() - 601)
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
    scored_exempt = judgment(continuity={
        'score': 2, 'evidence_ids': [], 'reason': 'No clarification was needed.'})
    assert scored_exempt.passes(known_ids={'turn-1'},
                               not_applicable=frozenset({'continuity'}))


def test_a_dotted_path_into_a_known_id_is_accepted_but_an_unrelated_path_is_not():
    known = {'turn-1', 'verified_facts_and_effects'}
    dotted = judgment(completeness={'score': 2,
        'evidence_ids': ['verified_facts_and_effects.persisted_draft.constraints'],
        'reason': 'Cites a nested path into a known fact group.'})
    assert dotted.passes(known_ids=known)
    unrelated = judgment(completeness={'score': 2,
        'evidence_ids': ['unknown_group.nested_field'], 'reason': 'Invents a root.'})
    assert not unrelated.passes(known_ids=known)


def test_a_colon_sub_reference_into_a_known_turn_id_is_accepted_but_a_similar_prefix_is_not():
    known = {'turn-1', 'shiftmind-live-abc:turn:1'}
    sub_reference = judgment(completeness={'score': 2,
        'evidence_ids': ['shiftmind-live-abc:turn:1:assistant:0'],
        'reason': 'Cites the first reply segment of a known turn.'})
    assert sub_reference.passes(known_ids=known)
    different_turn = judgment(completeness={'score': 2,
        'evidence_ids': ['shiftmind-live-abc:turn:10'],
        'reason': 'A different turn that merely shares a numeric prefix.'})
    assert not different_turn.passes(known_ids=known)


def test_missing_or_uncertain_judgments_are_not_automatic_passes():
    assert turn_verdict(factual_failures=[], judgment=None, known_ids={'turn-1'}) == 'incomplete'
    uncertain = judgment().model_copy(update={'verdict': 'uncertain'})
    assert turn_verdict(factual_failures=[], judgment=uncertain, known_ids={'turn-1'}) == 'needs_review'


def test_judgment_rejects_malformed_score_and_extra_provider_content():
    data = judgment().model_dump()
    data['relevance']['score'] = '2'
    with pytest.raises(ValidationError):
        ConversationJudgment.model_validate(data)


def test_judge_reason_is_bounded_but_allows_concise_multi_fact_explanations():
    accepted = judgment(completeness={
        'score': 2, 'evidence_ids': ['turn-1'], 'reason': 'x' * 1000})
    assert len(accepted.completeness.reason) == 1000
    # An over-long reason is TRUNCATED, not rejected: discarding it threw away a
    # whole judged turn (live-suite-v2-final-x3-c, A6 rep1).
    data = judgment().model_dump()
    data['completeness']['reason'] = 'x' * 1500
    truncated = ConversationJudgment.model_validate(data)
    assert len(truncated.completeness.reason) == 1000
    assert truncated.completeness.reason.endswith('...')
    data = judgment().model_dump()
    data['reasoning'] = 'must not enter evidence'
    with pytest.raises(ValidationError):
        ConversationJudgment.model_validate(data)


def test_one_garbled_citation_among_real_ones_does_not_fail_a_correct_turn():
    """Observed in live-suite-v2-final-x3: the judge mistyped its own isolation
    prefix, so an all-2s verdict with real citations failed the whole turn."""
    graded = judgment(relevance={'score': 2, 'reason': 'Cites the turn and a typo.',
                                 'evidence_ids': ['turn-4', 'turn-4-typo']})
    assert graded.passes(known_ids={'turn-1', 'turn-4'})
    assert graded.unknown_citations(known_ids={'turn-1', 'turn-4'}) == ['turn-4-typo']


def test_a_dimension_citing_only_invented_evidence_still_fails():
    invented = judgment(relevance={'score': 2, 'reason': 'Invents evidence.',
                                   'evidence_ids': ['turn-99', 'made-up']})
    assert not invented.passes(known_ids={'turn-1'})
    assert invented.unknown_citations(known_ids={'turn-1'}) == ['made-up', 'turn-99']


def test_admission_refuses_a_call_that_would_pass_any_ceiling_but_allows_one_that_just_fits():
    fits = lambda **used: (ConversationBudget(limits(), **used))
    # requests: 99 used + 1 reserved == the limit of 100
    fits(requests=99).admit(reserve_usd=.01, requests=1)
    with pytest.raises(IncompleteConversationRun, match='aggregate_budget_exhausted'):
        fits(requests=99).admit(reserve_usd=.01, requests=2)
    # tokens: 9900 used + 100 reserved == the limit of 10000
    fits(tokens=9900).admit(reserve_usd=.01, tokens=100)
    with pytest.raises(IncompleteConversationRun, match='aggregate_budget_exhausted'):
        fits(tokens=9900).admit(reserve_usd=.01, tokens=101)
    # spend: 1 prior + 5 spent + 1 reserved == the limit of 7
    fits(prior_spend_usd=1, spend_usd=5).admit(reserve_usd=1)
    with pytest.raises(IncompleteConversationRun, match='aggregate_budget_exhausted'):
        fits(prior_spend_usd=1, spend_usd=5).admit(reserve_usd=2)


def test_admission_needs_a_tool_call_left_but_charging_the_last_one_is_allowed():
    budget = ConversationBudget(limits())
    budget.charge(requests=1, tool_calls=100, tokens=0, cost_usd=0)  # exactly the limit: fine
    with pytest.raises(IncompleteConversationRun, match='aggregate_budget_exhausted'):
        budget.admit(reserve_usd=.01)  # but nothing further may start
    with pytest.raises(IncompleteConversationRun, match='aggregate_budget_exhausted'):
        budget.charge(requests=0, tool_calls=1, tokens=0, cost_usd=0)  # 101 is over


def test_charging_exactly_up_to_a_ceiling_is_not_exhaustion():
    budget = ConversationBudget(limits())
    budget.charge(requests=100, tool_calls=0, tokens=10000, cost_usd=7)
    assert (budget.requests, budget.tokens, budget.spend_usd) == (100, 10000, 7)


def test_admission_refuses_once_the_elapsed_ceiling_has_passed():
    ConversationBudget(limits()).admit(reserve_usd=.01)
    with pytest.raises(IncompleteConversationRun, match='aggregate_budget_exhausted'):
        ConversationBudget(limits(), started=monotonic() - 601).admit(reserve_usd=.01)


def test_prior_story_spend_counts_against_the_final_charge_too():
    budget = ConversationBudget(limits(), prior_spend_usd=3)
    with pytest.raises(IncompleteConversationRun, match='aggregate_budget_exhausted'):
        budget.charge(requests=1, tool_calls=0, tokens=0, cost_usd=4.01)


def test_the_case_limit_stops_a_further_execution():
    budget = ConversationBudget(replace(limits(), case_limit=2))
    budget.begin_execution()
    budget.begin_execution()
    with pytest.raises(IncompleteConversationRun, match='case_budget_exhausted'):
        budget.begin_execution()
    assert budget.executions == 2


def test_a_judged_fail_is_a_fail_even_when_every_dimension_scores_two():
    failed = judgment().model_copy(update={'verdict': 'fail'})
    assert not failed.passes(known_ids={'turn-1'})
    assert turn_verdict(factual_failures=[], judgment=failed, known_ids={'turn-1'}) == 'fail'
