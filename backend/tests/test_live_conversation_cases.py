"""The right-sized live-conversation catalogue (sprint-change-proposal-2026-09-17)."""
from dataclasses import replace

import pytest

from evals.live_conversations.cases import load_scenarios, prefix_executions, validate_scenarios


def test_catalogue_is_three_full_conversations():
    cases = load_scenarios()
    assert {case.id: len(case.turns) for case in cases} == {'A': 6, 'B': 12, 'C': 12}
    executions = tuple(prefix_executions(cases))
    assert len(executions) == 3
    assert sum(len(turns) for _, _, turns in executions) == 30
    for scenario, endpoint, turns in executions:
        assert endpoint == len(scenario.turns) and turns == scenario.turns
    assert [turn.user for turn in cases[0].turns[:3]] == [
        'HI my name is Minh', 'how can you help me?', 'how many work are therre?',
    ]
    assert 'Do not require both alternatives' in cases[0].turns[2].obligation


def test_b_is_one_complete_draft_solve_approve_cycle():
    b = {case.id: case for case in load_scenarios()}['B']
    actions = [action for turn in b.turns for action in turn.actions_after]
    assert actions == ['run_optimization', 'verify_baseline_unchanged', 'approve', 'reload']
    assert [index for index, turn in enumerate(b.turns, 1)
            if turn.obligation.startswith('Persist')] == [4, 6]


def test_c_runs_with_demonstration_and_allows_the_truthful_unapprovable_outcome():
    c = {case.id: case for case in load_scenarios()}['C']
    assert c.demonstration_enabled
    assert 'agent_cancelled' in c.turns[10].allowed_run_statuses
    assert all('agent_cancelled' not in turn.allowed_run_statuses
               for index, turn in enumerate(c.turns) if index != 10)


def test_a_partial_conversation_is_rejected():
    cases = load_scenarios()
    changed = replace(cases[1], prefixes=(4,))
    with pytest.raises(ValueError, match='complete conversation'):
        validate_scenarios((cases[0], changed, cases[2]))


def test_a_missing_scenario_is_rejected():
    cases = load_scenarios()
    with pytest.raises(ValueError, match='exactly'):
        validate_scenarios(cases[:2])


def test_an_unknown_action_is_rejected():
    cases = load_scenarios()
    turn = replace(cases[1].turns[6], actions_after=('run_optimisation',))
    changed = replace(cases[1], turns=(*cases[1].turns[:6], turn, *cases[1].turns[7:]))
    with pytest.raises(ValueError, match='unsupported authored actions'):
        validate_scenarios((cases[0], changed, cases[2]))


def test_resume_and_retry_are_offered_by_the_runner_cli():
    """A late infrastructure fault must cost one execution, not a whole run."""
    from evals.live_conversations.suite import _arguments

    args = _arguments(['--output', 'out.json'])
    assert args.resume is None and args.execution_retries == 2
    resumed = _arguments(['--output', 'out.json', '--resume', 'earlier.json',
                          '--execution-retries', '1'])
    assert resumed.resume.name == 'earlier.json' and resumed.execution_retries == 1
