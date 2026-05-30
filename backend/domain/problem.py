"""SchedulingProblem — the pure input the engine consumes."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List

from domain.types import DemandBand, Member, ShiftTemplate, Task


@dataclass
class SchedulingProblem:
    horizon_h: float                     # planning length (e.g. 48 for 2 days, 168 for a week)
    members: List[Member]
    tasks: List[Task]
    templates: List[ShiftTemplate]
    demand: List[DemandBand]

    # caps that vary by employment type (filled by adapter; defaults applied if absent)
    max_hours_per_week: Dict[str, float] = field(default_factory=dict)   # emp_type -> hours
    max_shifts_per_day: Dict[str, int] = field(default_factory=dict)     # emp_type -> count

    def task(self, task_id: str) -> Task | None:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None
