"""SolveResult and reporting types returned by the engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List


@dataclass(frozen=True)
class ScheduleRow:
    contact_id: str
    member_name: str
    task_id: str
    function: str
    shift_id: str
    start_h: float
    end_h: float


@dataclass
class CoverageStat:
    required_h: float
    served_h: float

    @property
    def pct(self) -> float:
        return (self.served_h / self.required_h) if self.required_h > 1e-9 else 1.0


@dataclass
class SummaryMetrics:
    coverage_by_function: Dict[str, CoverageStat] = field(default_factory=dict)
    coverage_by_day: Dict[int, float] = field(default_factory=dict)
    total_cost: float = 0.0
    total_unmet_hours: float = 0.0
    scheduled_shifts: int = 0
    scheduled_members: int = 0


@dataclass
class SolverStats:
    status: str
    wall_time_s: float
    unmet_objective_hours: float
    cost_objective: float


@dataclass
class SolveResult:
    status: str
    schedule: List[ScheduleRow]
    metrics: SummaryMetrics
    stats: SolverStats
