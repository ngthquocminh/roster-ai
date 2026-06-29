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

# Penalty per unit of headcount shortfall for set_min_workers_per_task overrides
# (soft round-2 term only — never round 1, never a hard constraint).
#
# Chosen large enough that assigning one extra body to clear a single-hour shortfall
# beats that body's marginal wage cost (a full shift: 8h * $40/h * COST_SCALE = 32_000),
# yet not so large it dominates the entire round-2 cost objective.
# Empirical calibration against the full-week fixture is deferred to Phase 4 (ENG-04).
MIN_WORKERS_PENALTY: int = 100_000

# Penalty for lock_worker_shift: soft round-2 penalty if member has zero shifts
# on the locked day. Same order of magnitude as MIN_WORKERS_PENALTY so the signal
# is visible against wage costs. Empirical calibration deferred to Phase 4 (ENG-04).
LOCK_SHIFT_PENALTY: int = 100_000

# Penalty per task-var assignment where excluded member is assigned to excluded task.
# Assignment vars are booleans; penalty fires once per assigned slot (not per hour).
# Set large enough to discourage assignment but below MIN_WORKERS_PENALTY so a
# round-1 coverage requirement can still override the exclusion.
EXCLUDE_WORKER_PENALTY: int = 50_000

# Penalty per VOL_SCALE unit of effective hours above the soft max_hours cap.
# Actual penalty per hour over limit = MAX_HOURS_PENALTY / VOL_SCALE = 1_000.
# Layered atop the existing HARD weekly cap (total can never exceed the hard cap).
# Empirical calibration deferred to Phase 4 (ENG-04).
MAX_HOURS_PENALTY: int = 100_000
