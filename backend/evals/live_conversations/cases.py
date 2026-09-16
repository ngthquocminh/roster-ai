"""Versioned user-only scenarios; every prefix generates its own live history."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DATASET = Path(__file__).parent / 'scenarios.json'


@dataclass(frozen=True)
class ConversationTurn:
    user: str
    obligation: str
    actions_after: tuple[str, ...] = ()


@dataclass(frozen=True)
class ConversationScenario:
    id: str
    prefixes: tuple[int, ...]
    turns: tuple[ConversationTurn, ...]


def validate_scenarios(scenarios: tuple[ConversationScenario, ...]) -> None:
    if len({case.id for case in scenarios}) != len(scenarios):
        raise ValueError('scenario identifiers must be unique')
    if len(scenarios) < 8:
        raise ValueError('at least eight distinct scenarios are required')
    for case in scenarios:
        if not case.turns or len(case.turns) not in case.prefixes:
            raise ValueError('every scenario must execute its complete conversation')
        if len(set(case.prefixes)) != len(case.prefixes):
            raise ValueError('prefix endpoints must be unique')
        if len(case.prefixes) < 5 or any(type(p) is not int or not 1 <= p <= len(case.turns) for p in case.prefixes):
            raise ValueError('five valid independent prefix endpoints are required')
        if any(not turn.user.strip() or not turn.obligation.strip() for turn in case.turns):
            raise ValueError('each turn requires user text and a semantic obligation')
    if max(len(case.turns) for case in scenarios) < 20:
        raise ValueError('a full twenty-turn conversation is required')


def load_scenarios(path: Path = DATASET) -> tuple[ConversationScenario, ...]:
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema_version') != '1':
        raise ValueError('unsupported conversation dataset version')
    cases = tuple(ConversationScenario(
        id=row['id'], prefixes=tuple(row['prefixes']),
        turns=tuple(ConversationTurn(
            user=turn['user'], obligation=turn['obligation'],
            actions_after=tuple(turn.get('actions_after', ())),
        ) for turn in row['turns']),
    ) for row in data['scenarios'])
    validate_scenarios(cases)
    return cases


def prefix_executions(scenarios):
    for case in scenarios:
        for endpoint in case.prefixes:
            yield case, endpoint, case.turns[:endpoint]
