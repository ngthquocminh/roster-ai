"""Distilled constants for the Scheduling Engine.

Values mirror the production model where they carry over; engine-specific
scaling knobs are grouped at the bottom.
"""
from __future__ import annotations

# --- scheduling rule defaults (per employment type, used when not specified) ---
DEFAULT_MAX_HOURS_PER_WEEK: float = 56.0
DEFAULT_MAX_SHIFTS_PER_DAY: int = 2
DEFAULT_MIN_GAP_HOURS: float = 2.0
WEEK_HOURS: float = 168.0

# --- productivity / coverage ---
DEFAULT_TASK_RATE: float = 10.0            # units/hour fallback when no rate known
ABSENTEEISM_FACTOR: float = 100.0 / 110.0  # flat ~10% absenteeism haircut on supply

# Task slots per shift by gross length (mirrors get_task_segment_count):
#   <= 6h -> 1 slot, > 6h -> 2 slots.
def task_slot_count(shift_length_h: float) -> int:
    return 1 if shift_length_h <= 6.0 else 2


# --- shift generation bounds (keep candidate count tractable) ---
SHIFT_START_GRID_H: float = 1.0     # candidate start times snapped to this grid
MAX_STARTS_PER_TEMPLATE: int = 6    # cap candidates per (window, template)

# --- integer scaling (CP-SAT is integer-only) ---
VOL_SCALE: int = 100        # volume & (rate*time) products -> ints
HOUR_SCALE: int = 100_000   # labour-hours in the objective -> ints
COST_SCALE: int = 100       # dollars -> cents
ROSTER_UNFILL_WEIGHT: int = 1  # small nudge (in scaled hours) to fill rosters in round 1
