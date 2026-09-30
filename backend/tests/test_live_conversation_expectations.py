"""Per-turn expectations: authored checks, bindings, and verdicts. HTTP doubles
and canned application state only; not live acceptance evidence."""
import json

import httpx
import pytest

from evals.live_conversations import runner
from evals.live_conversations.cases import (
    ConversationScenario, ConversationTurn, load_scenarios,
)
from evals.live_conversations.expectations import (
    Bindings, TurnContext, Unbound, apply_answers, code_check, evaluate, mentioned,
    parse_expectation, resolve, validate_turn_expectations, verdict_from_checks, visible_lines,
    visible_text,
)
from evals.live_conversations.jev_judge import TYPESAFE_JUDGE_ENDPOINT, ask_yes_no
from evals.live_conversations.protocol import ConversationBudget, IncompleteConversationRun
from evals.live_conversations.runner import execute_prefix
from evals.report import LiveSuiteBudgetV1
from tests.test_live_conversation_execute_prefix import (
    APPROVAL, CANDIDATE, COMPLETED, FakeApp, Telemetry, judgment,
)
from tests.test_live_conversation_protocol import limits

WORKERS = {'w1': 'Priya Nair', 'w2': 'Arjun Patel'}
TASKS = {'t1': 'Main Pick | Order Picker M02', 't2': 'Chiller Pick | Order Picker C02'}


def _entity(group, record_id):
    return {'group': group, 'record_id': record_id}


def _draft(*constraints, locks=(), summary='1 reversible constraint; preserved 0 existing locks.'):
    return {'proposal_id': 'p-1', 'constraints': list(constraints), 'preserved_locks': list(locks),
            'consequence_summary': summary}


EXCLUDE = {'kind': 'exclude_worker_from_task', 'description': 'Keep Priya Nair off Main Pick.',
           'max_hours': None, 'resolved_entities': [_entity('workers', 'w1'),
                                                    _entity('work-areas-and-tasks', 't1')]}
CAP = {'kind': 'set_max_hours', 'description': 'Cap Priya Nair at 40 hours per week.',
       'max_hours': 40.0, 'resolved_entities': [_entity('workers', 'w1')]}


def _reply(text):
    return {'activity_type': 'agent_response',
            'response': {'segments': [{'kind': 'prose', 'text': text}]}}


def _ctx(activity, *, draft=None, assignments=(), locks=(), reply_lines=None, rows=(), turn=5):
    return TurnContext(activity=activity, visible=runner.visible_activity(activity), draft=draft,
                       assignments=list(assignments), locks=list(locks), workers_by_id=WORKERS,
                       tasks_by_id=TASKS, reply_lines=reply_lines or {}, candidate_rows=list(rows),
                       turn=turn)


def _bound(**values):
    bindings = Bindings()  # bound at turn 0: earlier than any graded turn
    for name, value in values.items():
        bindings.bind(name, value)
    return bindings


def _e(**raw):
    return parse_expectation({'id': 'x', **raw})


# --- authoring: what the loader refuses ------------------------------------------------

@pytest.mark.parametrize('raw,message', [
    ({'check': 'teleport'}, 'unknown check'),
    ({'check': 'mentions', 'value': '{nope}'}, 'unknown bindings'),
    ({'check': 'judge', 'question': 'q?', 'want': False, 'facts': ['secrets']}, 'unknown facts'),
    ({'check': 'mentions'}, "needs \\['value'\\]"),
    ({'check': 'judge', 'question': 'q?'}, 'needs'),
    ({'check': 'judge', 'question': 'q?', 'want': 'yes'}, 'want must be true or false'),
    ({'check': 'mentions', 'value': 'x', 'colour': 'red'}, 'unknown expectation fields'),
    ({'check': 'mentions', 'value': 'x', 'facts': ['tasks']}, 'does not take'),
    ({'check': 'draft_has', 'kind': 'k', 'value': 'x'}, 'does not take'),
    ({'check': 'mentions_any', 'values': 'abc'}, 'must be a list of strings'),
    ({'check': 'mentions', 'value': ['a', 'b']}, 'non-empty string or number'),
    ({'check': 'mentions', 'value': '  '}, 'non-empty string or number'),
    ({'check': 'mentions', 'value': '{task_names}'}, 'needs mentions_all'),
    ({'check': 'draft_matches_turn', 'turn': '3'}, 'positive turn number'),
    ({'check': 'draft_has', 'kind': 'set_max_hours', 'max_hours': '40'}, 'max_hours must be a number'),
    ({'check': 'judge', 'question': 'Is `facts.tasks` complete?', 'want': True}, 'does not declare'),
])
def test_a_malformed_expectation_is_refused_at_load(raw, message):
    with pytest.raises(ValueError, match=message):
        parse_expectation({'id': 'x', **raw})


def test_a_turn_of_only_must_nots_is_refused():
    # tau-bench: a reply that does nothing passes every "must not".
    only_negative = (
        parse_expectation({'id': 'lies', 'check': 'judge', 'question': 'Does it lie?', 'want': False}),
        parse_expectation({'id': 'silent', 'check': 'mentions_none', 'values': ['x']}))
    with pytest.raises(ValueError, match='positive'):
        validate_turn_expectations(only_negative)


@pytest.mark.parametrize('raw', [{'check': 'mentions', 'value': 'x'}, {'id': 'x', 'value': 'x'},
                                 'mentions'])
def test_an_expectation_without_id_or_check_is_a_value_error(raw):
    with pytest.raises(ValueError):
        parse_expectation(raw)


def test_a_check_may_only_look_back_to_an_earlier_turn():
    looks_back = (_e(check='draft_matches_turn', turn=3),)
    validate_turn_expectations(looks_back, position=4)
    with pytest.raises(ValueError, match='not an earlier turn'):
        validate_turn_expectations(looks_back, position=3)


def test_duplicate_expectation_ids_are_refused():
    with pytest.raises(ValueError, match='duplicate'):
        validate_turn_expectations((_e(check='activity_is', activity='draft'),) * 2)


def test_every_scenario_carries_expectations_on_every_turn():
    scenarios = {case.id: case for case in load_scenarios()}
    assert set(scenarios) == set('ABCD')
    assert all(turn.expect for case in scenarios.values() for turn in case.turns)


# --- grounded claims, starting bindings, and C's draft checks ---------------------------

def _claim(metric, task_id=None, family=None, verdict='supported'):
    return {'kind': 'claim', 'metric': metric, 'verdict': verdict, 'value': 1, 'unit': 'u',
            'arguments': {'task_id': task_id, 'family': family}}


def _claiming(*claims):
    return {'activity_type': 'agent_response',
            'response': {'segments': [{'kind': 'prose', 'text': 'x'}, *claims]}}


def test_claims_metric_needs_a_supported_claim_of_that_metric_task_and_family():
    bindings = _bound(first_task_id='t1')
    check = _e(check='claims_metric', metric='staffed_minutes', task='{first_task_id}')
    assert code_check(check, _ctx(_claiming(_claim('staffed_minutes', 'T1'))), bindings)
    assert not code_check(check, _ctx(_claiming(_claim('staffed_minutes', 't2'))), bindings)
    assert not code_check(check, _ctx(_claiming(_claim('staffed_minutes', 't1', verdict='unsupported'))),
                          bindings)
    assert not code_check(check, _ctx(_reply('t1 has 2796 staffed minutes')), bindings)
    family = _e(check='claims_metric', metric='required_demand_volume', family='inbound')
    assert not code_check(family, _ctx(_claiming(_claim('required_demand_volume', 't1', 'outbound'))),
                          Bindings())


def test_start_binds_worker_facts_and_the_only_indirect_task():
    tasks = [{'record_id': 'T1', 'name': 'Main Pick'}, {'record_id': 'T2', 'name': 'Chiller Pick'}]
    bindings = Bindings()
    bindings.capture_start({}, tasks, [{'name': 'Priya Nair'}, {'name': 'Arjun Patel'}],
                           [{'task_id': 't2', 'family': 'indirect'}, {'task_id': 't1', 'family': 'outbound'}])
    assert bindings.get('worker_count') == 2
    assert bindings.get('worker_names') == ['Priya Nair', 'Arjun Patel']
    assert (bindings.get('indirect_task_id'), bindings.get('indirect_task')) == ('t2', 'Chiller Pick')
    two = Bindings()
    two.capture_start({}, tasks, [], [{'task_id': 't1', 'family': 'indirect'},
                                      {'task_id': 't2', 'family': 'indirect'}])
    with pytest.raises(Unbound):
        two.get('indirect_task')


def test_list_items_are_read_with_their_verified_names_on_the_same_line():
    # Live run a9cc7bf, A:6: split into segments, every bullet read as a lone "-".
    reply = {'activity_type': 'agent_response', 'response': {'segments': [
        {'kind': 'prose', 'text': 'Tasks:\n- '}, {'kind': 'fact', 'text': 'Main Pick | Order Picker M02'},
        {'kind': 'prose', 'text': ' — pick\n- '}, {'kind': 'fact', 'text': 'Chiller Pick | Order Picker C02'},
        {'kind': 'prose', 'text': ' — pick'}]}}
    check = _e(check='each_item_mentions', value='{task_names}')
    bindings = _bound(task_names=list(TASKS.values()))
    assert code_check(check, _ctx(reply), bindings)
    reply['response']['segments'].append({'kind': 'prose', 'text': '\n- Yard Sweep — sweeping'})
    assert not code_check(check, _ctx(reply), bindings)


def test_an_approval_event_names_the_baseline_it_replaced():
    # Live run 9b8dad2, B:12: a truthful "it replaced <old>" had no event behind it.
    bindings = Bindings()
    bindings.capture_decision({'approval_id': 'ap-1'}, approved=True, baseline_now='new',
                              baseline_before='old')
    assert bindings.events == ['Approval ap-1 approved by the user: the baseline is now new '
                               '(it replaced old).']


def test_the_first_outbound_volume_claim_fixes_the_conversations_task():
    tasks = [{'record_id': 'T1', 'name': 'Main Pick'}, {'record_id': 'T2', 'name': 'Chiller Pick'}]
    bindings = Bindings()
    bindings.capture_claims(_claiming(_claim('required_demand_volume', 'T2', 'inbound'),
                                      _claim('required_demand_volume', 'T1', 'outbound')), tasks)
    bindings.capture_claims(_claiming(_claim('required_demand_volume', 'T2', 'outbound')), tasks)
    assert (bindings.get('first_task_id'), bindings.get('first_task')) == ('t1', 'Main Pick')


MIN_TWO = {'kind': 'set_min_workers_per_task', 'n': 2, 'resolved_entities': [_entity('work-areas-and-tasks', 'T1')]}
SCALE = {'kind': 'scale_demand', 'factor': 1.1, 'resolved_entities': [_entity('work-areas-and-tasks', 'T1')]}


def test_draft_has_compares_n_and_factor():
    bindings = _bound(first_task_id='t1')
    ctx = _ctx(_reply('x'), draft=_draft(MIN_TWO, SCALE))
    assert code_check(_e(check='draft_has', kind='set_min_workers_per_task', task='{first_task_id}', n=2),
                      ctx, bindings)
    assert not code_check(_e(check='draft_has', kind='set_min_workers_per_task', n=3), ctx, bindings)
    assert code_check(_e(check='draft_has', kind='scale_demand', factor=1.1), ctx, bindings)
    assert not code_check(_e(check='draft_has', kind='scale_demand', factor=1.2), ctx, bindings)


def _lock(worker, start, end):
    return {'kind': 'lock_worker_shift', 'start_minute': start, 'end_minute': end,
            'resolved_entities': [_entity('workers', worker)]}


def test_a_roster_lock_needs_a_qualified_worker_on_one_of_their_own_roster_windows():
    workers = [
        {'record_id': 'W1', 'qualifications': [{'task_id': 'T1'}],
         'availability_windows': [{'kind': 'roster', 'start_minute': 300, 'end_minute': 810},
                                  {'kind': 'availability', 'start_minute': 900, 'end_minute': 1200}]},
        {'record_id': 'W2', 'qualifications': [{'task_id': 'T2'}],
         'availability_windows': [{'kind': 'roster', 'start_minute': 300, 'end_minute': 810}]},
    ]
    bindings = _bound(first_task_id='t1')
    check = _e(check='draft_has_roster_lock', task='{first_task_id}')

    def ok(lock):
        ctx = _ctx(_reply('x'), draft=_draft(MIN_TWO, lock))
        ctx.workers = workers
        return code_check(check, ctx, bindings)

    assert ok(_lock('w1', 300, 810))
    assert not ok(_lock('W1', 900, 1200))  # an availability window, not a roster one
    assert not ok(_lock('W1', 300, 800))   # not exactly the rostered window
    assert not ok(_lock('W2', 300, 810))   # not qualified for the task


# --- matching the visible reply ---------------------------------------------------------

def test_a_name_starting_a_line_still_matches_as_a_whole_token():
    # json.dumps once turned "\nPriya" into "\\npriya", which never matched.
    text = visible_text(runner.visible_activity(_reply('One assignment:\nPriya Nair works it.')))
    assert mentioned('Priya Nair', text)
    assert not mentioned('w1', visible_text('see w12'))
    # A hyphen joins a token: "40" alone is not the "40-hour" cap (B:12 names the forms).
    assert mentioned('40-hour', visible_text('capped at 40-hour weeks'))
    assert not mentioned('40', visible_text('capped at 40-hour weeks'))
    assert mentioned('Main Pick | Order Picker M02', visible_text('**Main Pick  |  Order Picker M02**'))


@pytest.mark.parametrize('term,text,expected', [
    ('76', 'coverage 0.76 overall', False),
    ('76', '76 assignments.', True),
    ('76', 'about 1,76 of them', False),
    ('jos', 'josé ran it', False),
    ('theo marsh', 'theo marsh-walker', False),
    ('c-1', 'candidate c-1-2', False),
    ('c-1', 'candidate c-1.', True),
])
def test_token_boundaries_reject_decimals_accents_and_hyphenated_extensions(term, text, expected):
    assert mentioned(term, text) is expected


def test_claim_arguments_are_part_of_the_visible_text():
    claim = {'activity_type': 'agent_response', 'response': {'segments': [
        {'kind': 'claim', 'metric': 'hours', 'arguments': {'worker': 'Priya Nair'}, 'value': 7.5,
         'unit': 'h', 'verdict': 'supported', 'result_id': 'r'}]}}
    text = visible_text(runner.visible_activity(claim))
    assert mentioned('Priya Nair', text) and mentioned('7.5', text)


# --- bindings ---------------------------------------------------------------------------

def test_bindings_are_set_once_and_never_from_none():
    bindings = Bindings()
    bindings.bind('candidate_id', None)
    with pytest.raises(Unbound):
        bindings.get('candidate_id')
    bindings.bind('candidate_id', 'first')
    bindings.bind('candidate_id', 'second')
    assert bindings.get('candidate_id') == 'first'
    with pytest.raises(KeyError):
        bindings.bind('not_a_binding', 1)


def test_the_first_saved_exclusion_binds_the_worker_and_task_and_the_latest_draft_is_kept():
    bindings = Bindings()
    bindings.capture_draft(_draft(EXCLUDE), WORKERS, TASKS)
    other = {**EXCLUDE, 'resolved_entities': [_entity('workers', 'w2'),
                                              _entity('work-areas-and-tasks', 't2')]}
    bindings.capture_draft(_draft(other, CAP, summary='later'), WORKERS, TASKS)
    assert bindings.get('excluded_worker') == 'Priya Nair'
    assert bindings.get('excluded_task_id') == 't1'
    assert bindings.draft['consequence_summary'] == 'later'
    assert len(bindings.events) == 2 and 'Cap Priya Nair at 40 hours' in bindings.events[1]


def test_two_exclusions_in_one_draft_bind_nothing():
    other = {**EXCLUDE, 'resolved_entities': [_entity('workers', 'w2'),
                                              _entity('work-areas-and-tasks', 't2')]}
    bindings = Bindings()
    bindings.capture_draft(_draft(EXCLUDE, other), WORKERS, TASKS)
    with pytest.raises(Unbound):
        bindings.get('excluded_worker')


def test_a_worker_missing_from_the_fixture_read_is_named_from_the_draft_label():
    labelled = {**EXCLUDE, 'resolved_entities': [
        {'group': 'workers', 'record_id': 'w9', 'label': 'Mia Wong (w9)'},
        {'group': 'work-areas-and-tasks', 'record_id': 't1', 'label': 'Main Pick (t1)'}]}
    bindings = Bindings()
    bindings.capture_draft(_draft(labelled), WORKERS, TASKS)
    assert bindings.get('excluded_worker') == 'Mia Wong'
    assert bindings.get('excluded_task') == 'Main Pick | Order Picker M02'  # the fixture wins


def test_a_later_draft_cannot_satisfy_keeping_an_exclusion_it_bound_itself():
    # Turn 4 saved no exclusion; turn 6's draft binds one. "Keeps the earlier
    # exclusion" must not pass by reading that exclusion from turn 6 itself.
    bindings = Bindings()
    bindings.turn = 6
    bindings.capture_draft(_draft(EXCLUDE, CAP), WORKERS, TASKS)
    keeps = _e(check='draft_has', kind='exclude_worker_from_task',
               worker='{excluded_worker_id}', task='{excluded_task_id}')
    with pytest.raises(Unbound):
        code_check(keeps, _ctx({'activity_type': 'draft'}, draft=_draft(EXCLUDE, CAP), turn=6),
                   bindings)
    assert code_check(keeps, _ctx({'activity_type': 'draft'}, draft=_draft(EXCLUDE, CAP), turn=7),
                      bindings)


def test_run_and_decision_bindings_and_events():
    bindings = Bindings()
    bindings.capture_run({'run': {'status': 'solver_cancelled'}, 'candidate': None}, None)
    with pytest.raises(Unbound):
        bindings.get('candidate_id')
    bindings.capture_run(COMPLETED, 1)
    assert bindings.get('candidate_id') == CANDIDATE and bindings.get('solver_status') == 'OPTIMAL'
    bindings.capture_approval_request(APPROVAL)
    bindings.capture_decision(APPROVAL, approved=True, baseline_now=CANDIDATE)
    assert bindings.get('promoted_baseline_id') == CANDIDATE
    assert bindings.get('approval_id') == 'ap-1'
    assert [event.split()[1] for event in bindings.events] == ['user', 'user', 'assistant', 'ap-1']


def test_resolve_keeps_a_whole_list_and_substitutes_inside_text():
    bindings = _bound(task_names=['A', 'B'], approval_id='ap-9')
    assert resolve('{task_names}', bindings) == ['A', 'B']
    assert resolve('one of {task_names}', bindings) == 'one of A, B'  # prose, not a repr
    assert resolve('give {approval_id} or a place', bindings) == 'give ap-9 or a place'
    with pytest.raises(Unbound):
        resolve('{candidate_id}', bindings)


# --- code checks ------------------------------------------------------------------------

@pytest.mark.parametrize('raw,text,expected', [
    ({'check': 'mentions', 'value': '{candidate_id}'}, 'candidate c-1 is ready', True),
    ({'check': 'mentions', 'value': '{candidate_id}'}, 'candidate c-10 is ready', False),
    ({'check': 'mentions_all', 'value': '{task_names}'}, 'Main Pick | Order Picker M02 only', False),
    ({'check': 'mentions_all', 'value': '{task_names}'},
     'Main Pick | Order Picker M02 and Chiller Pick | Order Picker C02', True),
    ({'check': 'mentions_any', 'values': ['{candidate_id}', '{assignment_count}']}, '76 rows', True),
    ({'check': 'mentions_none', 'values': ['{candidate_id}']}, 'nothing here', True),
])
def test_mention_checks(raw, text, expected):
    bindings = _bound(candidate_id='c-1', assignment_count=76, task_names=list(TASKS.values()))
    assert code_check(_e(**raw), _ctx(_reply(text)), bindings) is expected


def test_mentions_any_is_graded_on_what_is_bound_and_unbound_only_when_nothing_is():
    expectation = _e(check='mentions_any', values=['{candidate_id}', '{assignment_count}'])
    assert code_check(expectation, _ctx(_reply('76')), _bound(assignment_count=76))
    with pytest.raises(Unbound):
        code_check(expectation, _ctx(_reply('76')), Bindings())


def test_activity_checks():
    ctx = _ctx(APPROVAL)
    assert code_check(_e(check='activity_is', activity='approval_request'), ctx, Bindings())
    field = _e(check='activity_field_equals', field='candidate_schedule_version_id',
               value='{candidate_id}')
    assert code_check(field, ctx, _bound(candidate_id=CANDIDATE))
    assert not code_check(field, ctx, _bound(candidate_id='another'))


def test_draft_checks():
    bindings = _bound(excluded_worker_id='w1', excluded_task_id='t1')
    ctx = _ctx({'activity_type': 'draft'}, draft=_draft(EXCLUDE, CAP))
    assert code_check(_e(check='draft_has', kind='set_max_hours', worker='{excluded_worker_id}',
                         max_hours=40.0), ctx, bindings)
    assert not code_check(_e(check='draft_has', kind='set_max_hours', worker='{excluded_worker_id}',
                             max_hours=38.0), ctx, bindings)
    assert code_check(_e(check='draft_has', kind='exclude_worker_from_task',
                         worker='{excluded_worker_id}', task='{excluded_task_id}'), ctx, bindings)
    assert not code_check(_e(check='draft_has', kind='exclude_worker_from_task'),
                          _ctx(_reply('no draft here')), bindings)
    locks = [{'record_id': 'lock-1'}]
    kept = _ctx({'activity_type': 'draft'}, draft=_draft(EXCLUDE, locks=locks), locks=locks)
    dropped = _ctx({'activity_type': 'draft'}, draft=_draft(EXCLUDE), locks=locks)
    assert code_check(_e(check='draft_preserves_locks'), kept, bindings)
    assert not code_check(_e(check='draft_preserves_locks'), dropped, bindings)


def test_pair_checks():
    assignments = [{'worker_id': 'w1', 'task_id': 't1'}]
    assert code_check(_e(check='names_assigned_pair'),
                      _ctx(_reply('Priya Nair on Main Pick | Order Picker M02'), assignments=assignments),
                      Bindings())
    # A real worker and a real task that are NOT assigned together is not a pair.
    assert not code_check(_e(check='names_assigned_pair'),
                          _ctx(_reply('Priya Nair on Chiller Pick | Order Picker C02'),
                               assignments=assignments), Bindings())
    bindings = _bound(excluded_worker='Priya Nair', excluded_task='Main Pick | Order Picker M02')
    earlier = {3: visible_lines('Priya Nair works Main Pick | Order Picker M02')}
    assert code_check(_e(check='draft_matches_turn', turn=3), _ctx(_reply(''), reply_lines=earlier),
                      bindings)
    assert not code_check(_e(check='draft_matches_turn', turn=3),
                          _ctx(_reply(''), reply_lines={3: ['arjun patel']}), bindings)


def test_a_pair_must_be_named_together_not_anywhere_in_a_list():
    assignments = [{'worker_id': 'w1', 'task_id': 't1'}]
    listing = _reply('Workers: Priya Nair, Arjun Patel\n'
                     'Tasks: Main Pick | Order Picker M02, Chiller Pick | Order Picker C02')
    assert not code_check(_e(check='names_assigned_pair'), _ctx(listing, assignments=assignments),
                          Bindings())


# --- evaluation, answers and the verdict ------------------------------------------------

def test_evaluate_grades_code_now_and_asks_judges_over_reply_and_named_facts_only():
    expectations = (
        parse_expectation({'id': 'names', 'check': 'mentions', 'value': '{excluded_worker}'}),
        parse_expectation({'id': 'other', 'check': 'judge', 'want': False, 'facts': ['excluded_worker'],
                           'question': 'Does `reply` name a worker other than `facts.excluded_worker`?'}),
        parse_expectation({'id': 'record', 'check': 'mentions', 'value': '{approval_id}'}),
    )
    checks, questions, state = evaluate(expectations, _ctx(_reply('It was Priya Nair.')),
                                        _bound(excluded_worker='Priya Nair'), 'Who was it?')
    assert [(c['id'], c['outcome']) for c in checks] == [
        ('names', 'pass'), ('other', 'pending'), ('record', 'unbound')]
    assert checks[2]['binding'] == 'approval_id'
    # The facts ride inside THIS question's instructions, not in shared state.
    assert questions == {'other': {'type': 'noul', 'instructions': {
        'question': 'Does `reply` name a worker other than `facts.excluded_worker`?',
        'facts': {'excluded_worker': 'Priya Nair'}}}}
    assert set(state) == {'user_message', 'reply'}  # no transcript, no rules, no pooled facts


def test_no_judge_question_means_no_state():
    _checks, questions, state = evaluate(
        (_e(check='activity_is', activity='draft'),), _ctx({'activity_type': 'draft'}), Bindings(), 'u')
    assert questions == {} and state is None


@pytest.mark.parametrize('want,p_yes,outcome', [
    (True, .70, 'pass'), (True, .69, 'uncertain'), (True, .29, 'fail'),
    (False, .30, 'pass'), (False, .31, 'uncertain'), (False, .71, 'fail'),
])
def test_a_judge_check_is_scored_by_the_probability_of_the_wanted_answer(want, p_yes, outcome):
    checks = [{'id': 'q', 'check': 'judge', 'outcome': 'pending', 'want': want}]
    apply_answers(checks, {'q': p_yes})
    assert checks[0]['outcome'] == outcome


@pytest.mark.parametrize('outcomes,failures,verdict', [
    (['pass', 'pass'], [], 'pass'),
    (['pass', 'uncertain'], [], 'needs_review'),
    (['uncertain', 'unbound'], [], 'incomplete'),
    (['fail', 'unbound'], [], 'fail'),
    (['pass'], ['baseline_changed_before_approval'], 'fail'),
])
def test_the_verdict_puts_a_definite_failure_first(outcomes, failures, verdict):
    checks = [{'id': str(i), 'outcome': outcome} for i, outcome in enumerate(outcomes)]
    assert verdict_from_checks(checks, failures) == verdict


# --- the yes/no Jev call ----------------------------------------------------------------

def _noul_body(answers, input_tokens=500):
    return {'model': 'jev-1.13.0', 'usage': {'input_tokens': input_tokens, 'output_tokens': 5},
            'answers': {key: {'type': 'noul', 'noul': value} for key, value in answers.items()}}


def test_ask_yes_no_sends_one_request_of_nouls_and_charges_it():
    seen = []

    def handle(request):
        seen.append((str(request.url), json.loads(request.content)))
        return httpx.Response(200, json=_noul_body({'a': .9, 'b': .1}))

    budget = ConversationBudget(limits())
    questions = {'a': {'type': 'noul', 'instructions': 'A?'}, 'b': {'type': 'noul', 'instructions': 'B?'}}
    p_yes, usage = ask_yes_no(api_key='k', model='typesafe:jev-1.13.0', state={'reply': 'r'},
                              questions=questions, budget=budget,
                              client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert p_yes == {'a': .9, 'b': .1}
    assert seen[0][0] == TYPESAFE_JUDGE_ENDPOINT
    assert seen[0][1] == {'model': 'jev-1.13.0', 'state': {'reply': 'r'}, 'questions': questions}
    assert budget.requests == 1 and usage['attempts'][-1]['outcome'] == 'accepted'


def test_ask_yes_no_retries_a_missing_answer_once_then_is_incomplete():
    def handle(_request):
        return httpx.Response(200, json=_noul_body({'a': .9}))

    budget = ConversationBudget(limits())
    with pytest.raises(IncompleteConversationRun, match='judge_malformed_missing_answer_at_answers.b'):
        ask_yes_no(api_key='k', model='typesafe:jev-1.13.0', state={},
                   questions={'a': {'type': 'noul', 'instructions': 'A?'},
                              'b': {'type': 'noul', 'instructions': 'B?'}},
                   budget=budget, client=httpx.Client(transport=httpx.MockTransport(handle)))
    assert budget.requests == 2


# --- the runner path --------------------------------------------------------------------

def _drive(app, turns, *, judge_model, monkeypatch, p_yes=None):
    asked = []

    def fake_ask(**kwargs):
        asked.append(kwargs)
        return {key: (p_yes or {}).get(key, .95) for key in kwargs['questions']}, {'attempts': []}

    monkeypatch.setattr(runner, 'ask_yes_no', fake_ask)
    monkeypatch.setattr(runner, 'judge_turn', lambda **_kwargs: (judgment(), {'attempts': []}))
    monkeypatch.setattr(runner, 'judge_turn_jev', lambda **_kwargs: (judgment(), {'attempts': []}))
    case = ConversationScenario(id='X', prefixes=(len(turns),), turns=tuple(turns))
    report = execute_prefix(
        app=app, case=case, endpoint=len(turns), isolation_id='iso', telemetry=Telemetry(),
        judge_key='k', judge_model=judge_model, save=lambda _report: None,
        budget=ConversationBudget(LiveSuiteBudgetV1(
            case_limit=1, request_limit=50, tool_call_limit=50, token_limit=1000000,
            elapsed_seconds_limit=600, spend_usd_limit=5)))
    return report, asked


def _turn(user, *expect, actions=()):
    return ConversationTurn(user=user, obligation='o', actions_after=tuple(actions),
                            expect=tuple(parse_expectation(raw) for raw in expect))


RUN_THEN_ASK = [
    _turn('run it', {'id': 'directs', 'check': 'judge', 'want': True, 'question': 'Directs?'},
          actions=('run_optimization',)),
    _turn('what did it produce',
          {'id': 'status', 'check': 'mentions', 'value': '{solver_status}'},
          {'id': 'candidate', 'check': 'mentions', 'value': '{candidate_id}'}),
]


class _Scripted(FakeApp):
    """A FakeApp whose replies change per turn."""

    def __init__(self, replies, **kwargs):
        super().__init__(activity=replies[0], **kwargs)
        self.replies = list(replies)

    def send(self, user):
        self.activity = self.replies.pop(0)
        return super().send(user)


def test_under_a_typesafe_judge_expectation_turns_are_graded_by_their_checks(monkeypatch):
    app = _Scripted([_reply('Use the Run optimization control.'),
                     _reply(f'Candidate {CANDIDATE} is OPTIMAL.')])
    report, asked = _drive(app, RUN_THEN_ASK, judge_model='typesafe:jev-1.13.0',
                           monkeypatch=monkeypatch)
    first, second = report['turns']
    assert first['verdict'] == 'pass' and first['judgment'] is None
    assert first['checks'] == [{'id': 'directs', 'check': 'judge', 'outcome': 'pass', 'want': True,
                                'p_wanted': .95}]
    # Bound from the run the harness started AFTER turn 1's reply.
    assert [c['outcome'] for c in second['checks']] == ['pass', 'pass']
    assert second['verdict'] == 'pass'
    assert len(asked) == 1  # turn 2 is all code: no judge request
    assert set(asked[0]['state']) == {'user_message', 'reply'}


def test_a_value_bound_only_after_the_reply_is_not_visible_to_that_turn(monkeypatch):
    early = [_turn('run it', {'id': 'candidate', 'check': 'mentions', 'value': '{candidate_id}'},
                   actions=('run_optimization',))]
    report, _asked = _drive(_Scripted([_reply(f'Candidate {CANDIDATE}')]), early,
                            judge_model='typesafe:jev-1.13.0', monkeypatch=monkeypatch)
    assert report['turns'][0]['checks'][0]['outcome'] == 'unbound'
    assert report['turns'][0]['verdict'] == 'incomplete'


def test_a_code_miss_fails_the_turn(monkeypatch):
    app = _Scripted([_reply('Use the Run optimization control.'), _reply('It finished.')])
    report, _asked = _drive(app, RUN_THEN_ASK, judge_model='typesafe:jev-1.13.0',
                            monkeypatch=monkeypatch)
    assert report['turns'][1]['verdict'] == 'fail'
    assert report['status'] == 'failed'


def test_under_an_openrouter_judge_the_same_turns_use_the_holistic_judge(monkeypatch):
    app = _Scripted([_reply('Use the Run optimization control.'), _reply('It finished.')])
    report, asked = _drive(app, RUN_THEN_ASK, judge_model='openrouter:vendor/judge',
                           monkeypatch=monkeypatch)
    assert asked == []
    assert all('checks' not in row and row['judgment'] for row in report['turns'])


def test_a_judge_outage_leaves_the_turn_incomplete_with_its_checks(monkeypatch):
    def down(**_kwargs):
        raise IncompleteConversationRun('judge_unavailable_http_503')

    monkeypatch.setattr(runner, 'ask_yes_no', down)
    case = ConversationScenario(id='X', prefixes=(1,), turns=(RUN_THEN_ASK[0],))
    report = execute_prefix(
        app=_Scripted([_reply('Use the Run optimization control.')]), case=case, endpoint=1,
        isolation_id='iso', telemetry=Telemetry(), judge_key='k', judge_model='typesafe:jev-1.13.0',
        save=lambda _report: None, budget=ConversationBudget(LiveSuiteBudgetV1(
            case_limit=1, request_limit=50, tool_call_limit=50, token_limit=1000000,
            elapsed_seconds_limit=600, spend_usd_limit=5)))
    row = report['turns'][0]
    assert row['verdict'] == 'incomplete' and row['judge_unavailable_reason'] == 'judge_unavailable_http_503'
    assert row['checks'][0]['outcome'] == 'pending'


def test_checks_graded_before_an_aborting_action_stay_on_the_row(monkeypatch):
    # "approve" with no pending approval aborts the turn; its code checks were
    # already graded against the reply and must not be lost.
    turn = _turn('propose it', {'id': 'is_approval', 'check': 'activity_is',
                                'activity': 'approval_request'}, actions=('approve',))
    report, _asked = _drive(_Scripted([_reply('Done, it is your baseline.')]), [turn],
                            judge_model='typesafe:jev-1.13.0', monkeypatch=monkeypatch)
    assert report['incomplete_reason'] == 'required_agent_approval_missing'
    assert report['turns'][0]['checks'] == [
        {'id': 'is_approval', 'check': 'activity_is', 'outcome': 'fail'}]


def test_the_runner_binds_the_run_count_and_the_approval_it_observed(monkeypatch):
    turns = [
        _turn('run it', {'id': 'directs', 'check': 'judge', 'want': True, 'question': 'Directs?'},
              actions=('run_optimization',)),
        _turn('propose it', {'id': 'is_approval', 'check': 'activity_is',
                             'activity': 'approval_request'}, actions=('approve',)),
        _turn('what now',
              {'id': 'count', 'check': 'mentions', 'value': '{assignment_count} assignments'},
              {'id': 'baseline', 'check': 'mentions', 'value': '{promoted_baseline_id}'},
              {'id': 'approval', 'check': 'mentions', 'value': '{approval_id}'}),
    ]
    app = _Scripted([_reply('Use the Run optimization control.'), APPROVAL,
                     _reply(f'Baseline {CANDIDATE} (approval ap-1), 1 assignments.')])
    report, _asked = _drive(app, turns, judge_model='typesafe:jev-1.13.0', monkeypatch=monkeypatch)
    assert [row['verdict'] for row in report['turns']] == ['pass', 'pass', 'pass']
