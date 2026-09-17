"""Versioned user-only scenarios; every execution generates its own live history.

Right-sized 2026-09-17 (sprint-change-proposal-2026-09-17): each scenario runs as
one complete conversation. `prefixes` is kept as a one-element tuple holding the
full length so the runner's endpoint seam is unchanged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATASET = Path(__file__).parent / 'scenarios.json'
REQUIRED_SCENARIOS = {'A': 6, 'B': 12, 'C': 12}
SUPPORTED_ACTIONS = frozenset({
    'run_optimization', 'run_and_cancel', 'verify_baseline_unchanged', 'approve',
    'reject_approval', 'reload', 'reject_draft',
})
DEFAULT_RUN_STATUSES = ('agent_completed', 'approval_required')


@dataclass(frozen=True)
class ConversationTurn:
    user: str
    obligation: str
    actions_after: tuple[str, ...] = ()
    allowed_run_statuses: tuple[str, ...] = DEFAULT_RUN_STATUSES


@dataclass(frozen=True)
class ConversationScenario:
    id: str
    prefixes: tuple[int, ...]
    turns: tuple[ConversationTurn, ...]
    demonstration_enabled: bool = False


def validate_scenarios(scenarios: tuple[ConversationScenario, ...]) -> None:
    if len({case.id for case in scenarios}) != len(scenarios):
        raise ValueError('scenario identifiers must be unique')
    lengths = {case.id: len(case.turns) for case in scenarios}
    if lengths != REQUIRED_SCENARIOS:
        raise ValueError(f'scenarios must be exactly {REQUIRED_SCENARIOS}, got {lengths}')
    for case in scenarios:
        if case.prefixes != (len(case.turns),):
            raise ValueError('every scenario must execute its complete conversation only')
        for turn in case.turns:
            if not turn.user.strip() or not turn.obligation.strip():
                raise ValueError('each turn requires user text and a semantic obligation')
            unknown = set(turn.actions_after) - SUPPORTED_ACTIONS
            if unknown:
                raise ValueError(f'unsupported authored actions: {sorted(unknown)}')
            if not turn.allowed_run_statuses:
                raise ValueError('each turn must allow at least one agent run status')


def load_scenarios(path: Path = DATASET) -> tuple[ConversationScenario, ...]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != '2':
        raise ValueError('unsupported conversation dataset version')
    cases = tuple(ConversationScenario(
        id=row['id'], prefixes=(len(row['turns']),),
        demonstration_enabled=bool(row.get('demonstration_enabled', False)),
        turns=tuple(ConversationTurn(
            user=turn['user'], obligation=turn['obligation'],
            actions_after=tuple(turn.get('actions_after', ())),
            allowed_run_statuses=tuple(turn.get('allowed_run_statuses', DEFAULT_RUN_STATUSES)),
        ) for turn in row['turns']),
    ) for row in data['scenarios'])
    validate_scenarios(cases)
    return cases


def prefix_executions(scenarios):
    for case in scenarios:
        for endpoint in case.prefixes:
            yield case, endpoint, case.turns[:endpoint]
