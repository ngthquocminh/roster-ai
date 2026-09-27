"""Deterministic record -> text for the tier-1 checker (G' phase 3).

The same record always renders the same text, so a checker verdict is
reproducible. The handle (`ev`) is dropped: it is turn-local and means nothing
to a reader of the record.
"""
from __future__ import annotations

import json
from typing import Mapping

_LABEL = {
    "workers": "Worker",
    "tasks": "Task",
    "demand": "Demand interval",
    "assignments": "Baseline assignment",
    "locks": "Lock",
    "constraints": "Constraint",
}


def _render(value: object) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, sort_keys=True, ensure_ascii=False, default=str)


def verbalize_record(scenario_group: str, record: Mapping[str, object]) -> str:
    lines = [f"{_LABEL.get(scenario_group, scenario_group)} record"]
    lines.extend(
        f"{key}: {_render(value)}" for key, value in sorted(record.items()) if key != "ev"
    )
    return "\n".join(lines)


__all__ = ["verbalize_record"]
