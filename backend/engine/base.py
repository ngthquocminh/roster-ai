"""SchedulerEngine seam — the swap point for solver backends."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from domain.problem import SchedulingProblem
from domain.result import SolveResult


@dataclass
class SolverConfig:
    time_limit_s: float = 30.0
    num_workers: int = 8
    seed: int = 42


class SchedulerEngine(Protocol):
    def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult: ...

    @property
    def name(self) -> str: ...


def create_engine(name: str) -> SchedulerEngine:
    """Registry of available engines. Add a backend here to make it swappable."""
    if name == "cpsat":
        from engine.cpsat.engine import CpSatEngine
        return CpSatEngine()
    raise ValueError(f"Unknown solver engine: {name!r}. Available: ['cpsat']")
