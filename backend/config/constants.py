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
# Calibrated (Phase 4, ENG-04) via scripts/calibrate_penalties.py against the
# committed full-week fixture (data/sample_tiny_input.json). The wage-only
# baseline total_cost on that fixture is ~$11,549 (11 members, 6 tasks, 168h
# horizon). 100_000 is ~3.1x a single full shift's wage cost (8h * $40/h *
# COST_SCALE = 32_000) — large enough that adding one extra body to clear a
# single-hour shortfall beats that body's marginal wage cost — and ~8.7% of
# baseline_total_cost * COST_SCALE (1_154_900), well short of "two-plus orders
# of magnitude larger than baseline" (Pitfall 4). Sweeping this scale across the
# committed SCALES grid (10_000 .. 500_000, up to 5x) against the same
# fixture/override produced no change in the resulting schedule: this fixture's
# supply is scarce enough that round 1's
# unmet-hours lock leaves round 2 no slack to reallocate a body onto the
# overridden task regardless of penalty magnitude, so raising the constant
# further only makes the CP-SAT search harder without changing behavior.
# 100_000 is confirmed as the calibrated value.
MIN_WORKERS_PENALTY: int = 100_000

# Penalty for lock_worker_shift: soft round-2 penalty if member has zero shifts
# on the locked day. Calibrated (ENG-04) alongside MIN_WORKERS_PENALTY via
# scripts/calibrate_penalties.py: same order of magnitude keeps the signal
# visible against wage costs (a full shift ~$320, vs. this constant's
# $1,000-per-hour-missing equivalent) without exceeding the "small multiple of
# baseline total_cost" bound (Pitfall 4). 100_000 is confirmed as the
# calibrated value.
LOCK_SHIFT_PENALTY: int = 100_000

# Penalty per task-var assignment where excluded member is assigned to excluded task.
# Assignment vars are booleans; penalty fires once per assigned slot (not per hour).
# Calibrated (ENG-04): empirically, excluding a member with no idle qualified
# replacement on the full-week fixture (backend/tests/test_penalty_calibration.py
# ::test_unsatisfiable_override_degrades_gracefully) leaves the assignment
# unchanged (round 1's lock has no slack to reallocate) and adds a bounded
# cost delta of exactly EXCLUDE_WORKER_PENALTY * assigned_slots / COST_SCALE
# ($3,000 for 6 slots — ~26% of baseline total_cost, comfortably within the
# "small multiple, not dominating" bound). Kept below MIN_WORKERS_PENALTY so a
# round-1 coverage requirement can still override the exclusion. 50_000 is
# confirmed as the calibrated value.
EXCLUDE_WORKER_PENALTY: int = 50_000

# Penalty per VOL_SCALE unit of effective hours above the soft max_hours cap.
# Actual penalty per hour over limit = MAX_HOURS_PENALTY / VOL_SCALE = 1_000.
# Layered atop the existing HARD weekly cap (total can never exceed the hard cap).
# Calibrated (ENG-04) via scripts/calibrate_penalties.py using the same
# wage-cost-relative reasoning as MIN_WORKERS_PENALTY/LOCK_SHIFT_PENALTY: $1,000
# per hour over cap is well above the ~$40-50/h wage rate (so paying a member
# overtime-equivalent wages elsewhere beats absorbing the overflow penalty) yet
# the overflow var itself stays bounded (hard_cap - max_hours) * VOL_SCALE, so
# even a fully-saturated overflow can never approach "two-plus orders of
# magnitude larger than baseline" (Pitfall 4). 100_000 is confirmed as the
# calibrated value.
MAX_HOURS_PENALTY: int = 100_000
