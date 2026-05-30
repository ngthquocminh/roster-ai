"""Pure domain types for the Scheduling Engine.

No solver or web imports. All times are **hours from scenario start**
(e.g. day-1 17:30 = 17.5, day-2 06:00 = 30.0).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Tuple


class WindowKind(str, Enum):
    ROSTER = "roster"              # committed window — should be filled
    AVAILABILITY = "availability"  # optional window


@dataclass(frozen=True)
class Window:
    """A member's roster or availability window."""
    id: str
    start_h: float
    end_h: float
    kind: WindowKind

    @property
    def length_h(self) -> float:
        return self.end_h - self.start_h


@dataclass(frozen=True)
class Break:
    """A break inside a shift template, offset from shift start."""
    start_offset_h: float
    duration_h: float
    paid: bool


@dataclass(frozen=True)
class ShiftTemplate:
    id: str
    name: str
    length_h: float                       # gross length (incl. breaks)
    breaks: Tuple[Break, ...] = ()

    @property
    def unpaid_break_h(self) -> float:
        return sum(b.duration_h for b in self.breaks if not b.paid)

    @property
    def effective_h(self) -> float:
        """Worked (payable-for-coverage) hours = gross minus unpaid breaks."""
        return max(0.0, self.length_h - self.unpaid_break_h)


@dataclass(frozen=True)
class Qualification:
    task_id: str
    rate: float          # units/hour this member produces on this task
    preferred: bool = False


@dataclass
class Member:
    contact_id: str
    name: str
    emp_type: str                 # e.g. "Casual", "Agency", "Full Time"
    grade_id: str
    eba_id: str
    contracted_hours: float
    wage_per_hour: float          # $/hr (EBA Grade Rate, Base Rate)
    windows: List[Window] = field(default_factory=list)
    qualifications: List[Qualification] = field(default_factory=list)

    def rate_for(self, task_id: str) -> float | None:
        for q in self.qualifications:
            if q.task_id == task_id:
                return q.rate
        return None

    @property
    def rosters(self) -> List[Window]:
        return [w for w in self.windows if w.kind == WindowKind.ROSTER]

    @property
    def availabilities(self) -> List[Window]:
        return [w for w in self.windows if w.kind == WindowKind.AVAILABILITY]


@dataclass(frozen=True)
class Task:
    task_id: str
    name: str
    function: str         # e.g. "Pick", "Receiving", "Despatch", "Putaways"
    area_id: str
    unit_id: str | None = None


class DemandFamily(str, Enum):
    OUTBOUND = "outbound"
    INBOUND = "inbound"
    INDIRECT = "indirect"


@dataclass(frozen=True)
class DemandBand:
    """A demand requirement over a time window.

    For OUTBOUND/INBOUND `amount` is volume (units). For INDIRECT `amount` is
    required headcount.
    """
    task_id: str
    family: DemandFamily
    start_h: float
    end_h: float
    amount: float
    order_id: str = ""

    @property
    def duration_h(self) -> float:
        return self.end_h - self.start_h
