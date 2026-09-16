"""The natural-conversation matrix preserves independent, real user prefixes."""
from dataclasses import replace

import pytest

from evals.live_conversations.cases import load_scenarios, prefix_executions, validate_scenarios


def test_catalogue_preserves_all_narratives_lengths_and_independent_prefixes():
    cases = load_scenarios()
    assert {case.id: len(case.turns) for case in cases} == {
        'A': 6, 'B': 20, 'C': 12, 'D': 8, 'E': 10, 'F': 16, 'G': 7, 'H': 14,
    }
    prefixes = tuple(prefix_executions(cases))
    assert len(prefixes) == 40
    assert sum(len(turns) for _, _, turns in prefixes) == 273
    assert [turn.user for turn in cases[0].turns[:3]] == [
        'HI my name is Minh', 'how can you help me?', 'how many work are therre?',
    ]
    for scenario, endpoint, turns in prefixes:
        assert turns == scenario.turns[:endpoint]
        assert len(turns) == endpoint
        assert all(turn.obligation.strip() for turn in turns)


def test_missing_full_length_prefix_is_rejected():
    cases = load_scenarios()
    changed = replace(cases[0], prefixes=cases[0].prefixes[:-1])
    with pytest.raises(ValueError, match='complete conversation'):
        validate_scenarios((changed, *cases[1:]))


def test_duplicate_prefix_cannot_pad_execution_count():
    cases = load_scenarios()
    changed = replace(cases[0], prefixes=(2, 3, 4, 6, 6))
    with pytest.raises(ValueError, match='unique'):
        validate_scenarios((changed, *cases[1:]))
