"""Builds the CP-SAT model (variables + constraints) from a SchedulingProblem.

Time is in hours; CP-SAT is integer-only, so volumes/rates are scaled (see
config.constants). Shifts are generated per (member, window, template, start);
each selected shift carries at most one task per working slot.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from ortools.sat.python import cp_model

from config import constants as C
from domain.overrides import OverrideCall
from domain.problem import SchedulingProblem
from domain.types import DemandFamily, Member, ShiftTemplate, Window

Interval = Tuple[float, float]


# ----------------------------- interval helpers -----------------------------
def _overlap(a: Interval, b: Interval) -> float:
    return max(0.0, min(a[1], b[1]) - max(a[0], b[0]))


def _subtract(base: Interval, holes: List[Interval]) -> List[Interval]:
    """Return `base` minus any overlapping `holes`, as a list of intervals."""
    segments = [base]
    for hs, he in sorted(holes):
        out: List[Interval] = []
        for s, e in segments:
            if he <= s or hs >= e:        # no overlap
                out.append((s, e))
                continue
            if hs > s:
                out.append((s, hs))
            if he < e:
                out.append((he, e))
        segments = out
    return [(s, e) for s, e in segments if e - s > 1e-9]


def _split_into_slots(working: List[Interval], n_slots: int) -> List[List[Interval]]:
    """Split contiguous working intervals into n_slots groups by ~equal duration."""
    if n_slots <= 1 or len(working) <= 1:
        return [working]
    total = sum(e - s for s, e in working)
    target = total / n_slots
    groups: List[List[Interval]] = []
    cur: List[Interval] = []
    acc = 0.0
    for seg in working:
        cur.append(seg)
        acc += seg[1] - seg[0]
        if acc >= target - 1e-9 and len(groups) < n_slots - 1:
            groups.append(cur)
            cur, acc = [], 0.0
    if cur:
        groups.append(cur)
    return groups


# ----------------------------- var wrappers ---------------------------------
@dataclass
class ShiftVar:
    var: cp_model.IntVar
    member: Member
    window: Window
    template: ShiftTemplate
    start_h: float
    end_h: float
    eff_h: float                       # gross length minus unpaid breaks (for cost/caps)
    working: List[Interval]            # worked intervals (breaks removed)
    slots: List[List[Interval]] = field(default_factory=list)


@dataclass
class TaskVar:
    var: cp_model.IntVar
    shift: ShiftVar
    task_id: str
    slot_idx: int
    start_h: float
    end_h: float
    hour_overlap: Dict[int, float]     # hour -> worked hours on this task in that hour


# ----------------------------- builder --------------------------------------
class CpSatBuilder:
    def __init__(self, problem: SchedulingProblem, overrides: list[OverrideCall] | None = None):
        self.p = problem
        self.overrides: list[OverrideCall] = overrides or []
        self.m = cp_model.CpModel()
        self.shift_vars: List[ShiftVar] = []
        self.task_vars: List[TaskVar] = []
        self.unfilled_roster: Dict[str, cp_model.IntVar] = {}   # window.id -> bool
        self.unmet_vol: Dict[Tuple[str, int], cp_model.IntVar] = {}
        self.unmet_hc: Dict[Tuple[str, int], cp_model.IntVar] = {}
        # objective expressions (filled by build())
        self.round1_unmet = None
        self.round2_cost = None
        # precomputed reference rate per task (avg qualified rate) for unmet->hours
        self._ref_rate: Dict[str, float] = {}
        # coverage_terms exposed for _build_objectives; set by build() (D-02)
        self.coverage_terms: Dict[Tuple[str, int], List[Tuple[cp_model.IntVar, float]]] = {}

    # ---- demand aggregation ----
    def _aggregate_demand(self):
        # scale_demand overrides: per-task factor applied here (D-10).
        # SchedulingProblem stays immutable; unmet slack absorbs resulting shortfall,
        # so no factor value can make the model infeasible (OQ-1/T-02-05).
        scale: dict[str, float] = {
            o.args["task_id"]: float(o.args["factor"])
            for o in self.overrides if o.tool == "scale_demand"
        }

        vol: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
        hc: Dict[str, Dict[int, float]] = defaultdict(lambda: defaultdict(float))
        is_ind: Dict[str, bool] = {}
        for b in self.p.demand:
            f = scale.get(b.task_id, 1.0)          # factor=1.0 when no override
            h0, h1 = int(math.floor(b.start_h)), int(math.ceil(b.end_h))
            if b.family == DemandFamily.INDIRECT:
                is_ind[b.task_id] = True
                for h in range(h0, h1):
                    if _overlap((b.start_h, b.end_h), (h, h + 1)) > 0:
                        hc[b.task_id][h] += b.amount * f
            else:
                is_ind.setdefault(b.task_id, False)
                dur = max(b.duration_h, 1e-9)
                for h in range(h0, h1):
                    ov = _overlap((b.start_h, b.end_h), (h, h + 1))
                    if ov > 0:
                        vol[b.task_id][h] += b.amount * f * ov / dur
        return vol, hc, is_ind

    def _compute_ref_rates(self):
        sums: Dict[str, List[float]] = defaultdict(list)
        for m in self.p.members:
            for q in m.qualifications:
                sums[q.task_id].append(q.rate)
        for tid, rates in sums.items():
            self._ref_rate[tid] = (sum(rates) / len(rates)) if rates else C.DEFAULT_TASK_RATE

    # ---- shift generation ----
    def _candidate_starts(self, window: Window, tpl: ShiftTemplate) -> List[float]:
        latest = window.end_h - tpl.length_h
        if latest < window.start_h - 1e-9:
            return []
        grid = C.SHIFT_START_GRID_H
        first = window.start_h
        starts = [first]
        g = math.ceil(window.start_h / grid) * grid
        while g <= latest + 1e-9:
            if g > first + 1e-9:
                starts.append(round(g, 4))
            g += grid
        if latest - 1e-9 > starts[-1]:
            starts.append(round(latest, 4))
        # dedupe + cap
        uniq = sorted(set(round(s, 4) for s in starts if window.start_h - 1e-9 <= s <= latest + 1e-9))
        return uniq[: C.MAX_STARTS_PER_TEMPLATE]

    def _make_shift(self, member: Member, window: Window, tpl: ShiftTemplate, start: float) -> ShiftVar:
        end = start + tpl.length_h
        holes = [(start + b.start_offset_h, start + b.start_offset_h + b.duration_h) for b in tpl.breaks]
        working = _subtract((start, end), holes)
        n_slots = C.task_slot_count(tpl.length_h)
        slots = _split_into_slots(working, n_slots)
        name = f"shift_{member.contact_id[:6]}_{window.id}_{tpl.id[:6]}_{int(start*10)}"
        sv = ShiftVar(
            var=self.m.NewBoolVar(name),
            member=member, window=window, template=tpl,
            start_h=start, end_h=end, eff_h=tpl.effective_h,
            working=working, slots=slots,
        )
        return sv

    def build(self):
        vol_demand, hc_demand, is_ind = self._aggregate_demand()
        self._compute_ref_rates()
        self.vol_demand, self.hc_demand, self.is_ind = vol_demand, hc_demand, is_ind
        demanded_tasks = set(vol_demand) | set(hc_demand)

        coverage_terms: Dict[Tuple[str, int], List[Tuple[cp_model.IntVar, float]]] = defaultdict(list)

        # ----- generate shifts + task vars -----
        for member in self.p.members:
            qual_ids = {q.task_id for q in member.qualifications} & demanded_tasks
            if not qual_ids:
                continue
            for window in member.windows:
                for tpl in self.p.templates:
                    for start in self._candidate_starts(window, tpl):
                        sv = self._make_shift(member, window, tpl, start)
                        by_slot: Dict[int, List[cp_model.IntVar]] = defaultdict(list)
                        for slot_idx, slot in enumerate(sv.slots):
                            for tid in qual_ids:
                                # hour overlap of this task's slot working time
                                hour_ov: Dict[int, float] = {}
                                for seg in slot:
                                    h0, h1 = int(math.floor(seg[0])), int(math.ceil(seg[1]))
                                    for h in range(h0, h1):
                                        ov = _overlap(seg, (h, h + 1))
                                        if ov > 0:
                                            hour_ov[h] = hour_ov.get(h, 0.0) + ov
                                # keep only if this task has demand in a covered hour
                                if not any((tid in vol_demand and vol_demand[tid].get(h)) or
                                           (tid in hc_demand and hc_demand[tid].get(h))
                                           for h in hour_ov):
                                    continue
                                tv = TaskVar(
                                    var=self.m.NewBoolVar(f"task_{sv.var.Name()}_{tid[:6]}_{slot_idx}"),
                                    shift=sv, task_id=tid, slot_idx=slot_idx,
                                    start_h=slot[0][0], end_h=slot[-1][1], hour_overlap=hour_ov,
                                )
                                self.task_vars.append(tv)
                                by_slot[slot_idx].append(tv.var)
                                self.m.Add(tv.var <= sv.var)               # task only if shift
                                rate = member.rate_for(tid) or C.DEFAULT_TASK_RATE
                                for h, ov in hour_ov.items():
                                    if is_ind.get(tid):
                                        coverage_terms[(tid, h)].append((tv.var, 1.0))     # headcount
                                    else:
                                        coeff = rate * ov * C.ABSENTEEISM_FACTOR
                                        coverage_terms[(tid, h)].append((tv.var, coeff))   # volume
                        if not by_slot:
                            continue  # drop shift candidates that can do no demanded work
                        self.shift_vars.append(sv)
                        shift_task_vars = []
                        for slot_idx, vars_ in by_slot.items():
                            self.m.Add(sum(vars_) <= sv.var)               # <=1 task per slot
                            shift_task_vars.extend(vars_)
                        self.m.Add(sum(shift_task_vars) >= sv.var)         # no empty selected shift

        # Store coverage_terms before building objectives so _build_objectives
        # can reuse the per-(task,hour) body-count expressions for the shortfall
        # penalty (D-02).
        self.coverage_terms = coverage_terms
        self._add_window_and_cap_constraints()
        self._add_coverage_constraints(vol_demand, hc_demand, is_ind, coverage_terms)
        self._build_objectives(is_ind)
        return self

    # ----- window fill, per-day, weekly-hours, min-gap -----
    def _add_window_and_cap_constraints(self):
        shifts_by_window: Dict[str, List[ShiftVar]] = defaultdict(list)
        shifts_by_member: Dict[str, List[ShiftVar]] = defaultdict(list)
        for sv in self.shift_vars:
            shifts_by_window[sv.window.id].append(sv)
            shifts_by_member[sv.member.contact_id].append(sv)

        # roster fill (soft) / availability at-most-one
        seen_windows = {sv.window.id: sv.window for sv in self.shift_vars}
        for wid, window in seen_windows.items():
            svs = shifts_by_window[wid]
            if window.kind.value == "roster":
                u = self.m.NewBoolVar(f"unfilled_{wid}")
                self.unfilled_roster[wid] = u
                self.m.Add(sum(s.var for s in svs) + u == 1)
            else:
                self.m.Add(sum(s.var for s in svs) <= 1)

        for cid, svs in shifts_by_member.items():
            member = svs[0].member
            # per-day max shifts
            by_day: Dict[int, List[cp_model.IntVar]] = defaultdict(list)
            for sv in svs:
                by_day[int(sv.start_h // 24)].append(sv.var)
            max_day = self.p.max_shifts_per_day.get(member.emp_type, C.DEFAULT_MAX_SHIFTS_PER_DAY)
            for day, vars_ in by_day.items():
                self.m.Add(sum(vars_) <= max_day)
            # weekly effective-hours cap (scaled to ints)
            cap = self.p.max_hours_per_week.get(member.emp_type, C.DEFAULT_MAX_HOURS_PER_WEEK)
            self.m.Add(sum(int(round(sv.eff_h * C.VOL_SCALE)) * sv.var for sv in svs)
                       <= int(round(cap * C.VOL_SCALE)))
            # min gap: forbid two selected shifts closer than the gap
            for i in range(len(svs)):
                for j in range(i + 1, len(svs)):
                    a, b = svs[i], svs[j]
                    gap = max(a.start_h, b.start_h) - min(a.end_h, b.end_h)
                    if gap < C.DEFAULT_MIN_GAP_HOURS - 1e-9:
                        self.m.Add(a.var + b.var <= 1)

    # ----- coverage -----
    def _add_coverage_constraints(self, vol_demand, hc_demand, is_ind, coverage_terms):
        for tid, per_hour in vol_demand.items():
            if is_ind.get(tid):
                continue
            for h, dvol in per_hour.items():
                if dvol <= 1e-9:
                    continue
                rhs = int(round(dvol * C.VOL_SCALE))
                terms = coverage_terms.get((tid, h), [])
                supply = [int(round(coeff * C.VOL_SCALE)) * var for var, coeff in terms]
                unmet = self.m.NewIntVar(0, rhs, f"unmet_vol_{tid[:6]}_{h}")
                self.unmet_vol[(tid, h)] = unmet
                self.m.Add(sum(supply) + unmet >= rhs)
        for tid, per_hour in hc_demand.items():
            for h, dhc in per_hour.items():
                req = int(round(dhc))
                if req <= 0:
                    continue
                terms = coverage_terms.get((tid, h), [])
                supply = [var for var, _ in terms]
                unmet = self.m.NewIntVar(0, req, f"unmet_hc_{tid[:6]}_{h}")
                self.unmet_hc[(tid, h)] = unmet
                self.m.Add(sum(supply) + unmet >= req)

    # ----- objectives (scaled integer expressions) -----
    def _build_objectives(self, is_ind):
        unmet_terms = []
        for (tid, h), var in self.unmet_vol.items():
            ref = max(self._ref_rate.get(tid, C.DEFAULT_TASK_RATE), 1e-9)
            # scaled labour-hours = (unmet_scaled_vol / VOL_SCALE / ref) * HOUR_SCALE
            coeff = max(1, int(round(C.HOUR_SCALE / (C.VOL_SCALE * ref))))
            unmet_terms.append(coeff * var)
        for (tid, h), var in self.unmet_hc.items():
            unmet_terms.append(C.HOUR_SCALE * var)   # 1 headcount-hour
        for wid, u in self.unfilled_roster.items():
            window = next(sv.window for sv in self.shift_vars if sv.window.id == wid)
            coeff = max(1, int(round(window.length_h * C.HOUR_SCALE)))
            unmet_terms.append(coeff * u)
        self.round1_unmet = sum(unmet_terms) if unmet_terms else 0

        cost_terms = [
            int(round(sv.eff_h * sv.member.wage_per_hour * C.COST_SCALE)) * sv.var
            for sv in self.shift_vars
        ]

        # --- soft penalty terms for NL-derived overrides (D-02/D-03) ---
        # All terms added to round2_cost ONLY — never to round1_unmet, never as
        # hard constraints.  Because round 1 is locked before round 2 is minimised
        # (objective.py), these terms can never affect round-1 feasibility; an
        # override can therefore never make the solve infeasible (T-01-E1/T-02-05..T-02-08).
        # scale_demand is handled in _aggregate_demand, not here (D-10).
        shortfall_terms = []    # set_min_workers_per_task (existing)
        lock_terms = []         # lock_worker_shift (new)
        excl_terms = []         # exclude_worker_from_task (new)
        maxh_terms = []         # set_max_hours (new)

        for ov in self.overrides:
            if ov.tool == "set_min_workers_per_task":
                tid = ov.args["task_id"]
                n = int(ov.args["n"])
                # hours with demand for this task (union of vol and hc demand)
                hours = set(self.vol_demand.get(tid, {})) | set(self.hc_demand.get(tid, {}))
                for h in hours:
                    # body count: bare vars (coeff ignored) — headcount form (D-02)
                    bodies = [var for var, _ in self.coverage_terms.get((tid, h), [])]
                    # slack bounded by n so an empty supply degrades to a constant
                    # penalty rather than causing infeasibility (T-01-E1)
                    short = self.m.NewIntVar(0, n, f"minw_short_{tid[:6]}_{h}")
                    self.m.Add(sum(bodies) + short >= n)
                    shortfall_terms.append(short)

            elif ov.tool == "lock_worker_shift":
                # Soft penalty if member works zero shifts on the locked day (D-07).
                # absent=1 when no shift candidates exist for that day — penalty fires
                # but model stays feasible (bounded-slack guarantee, Pitfall 2).
                mid = ov.args["member_id"]
                day = int(ov.args["day"])
                day_shifts = [
                    sv for sv in self.shift_vars
                    if sv.member.contact_id == mid and int(sv.start_h // 24) == day
                ]
                absent = self.m.NewBoolVar(f"lock_absent_{mid[:6]}_{day}")
                self.m.Add(sum(sv.var for sv in day_shifts) + absent >= 1)
                lock_terms.append(absent)

            elif ov.tool == "exclude_worker_from_task":
                # Direct penalty on task assignment vars — no new slack needed (D-08).
                mid = ov.args["member_id"]
                tid = ov.args["task_id"]
                excl_vars = [
                    tv.var for tv in self.task_vars
                    if tv.shift.member.contact_id == mid and tv.task_id == tid
                ]
                excl_terms.extend(excl_vars)

            elif ov.tool == "set_max_hours":
                # Bounded overflow var above soft cap, layered under the hard cap (D-09/Pitfall 3).
                mid = ov.args["member_id"]
                max_h = float(ov.args["max_hours"])
                member_svs = [sv for sv in self.shift_vars if sv.member.contact_id == mid]
                if not member_svs:
                    continue
                emp_type = member_svs[0].member.emp_type
                hard_cap = self.p.max_hours_per_week.get(emp_type, C.DEFAULT_MAX_HOURS_PER_WEEK)
                scaled_max = int(round(max_h * C.VOL_SCALE))
                hard_cap_scaled = int(round(hard_cap * C.VOL_SCALE))
                # overflow var bounded by (hard_cap - max_hours)*VOL_SCALE, never
                # an arbitrary large constant — prevents the solver from absorbing
                # unlimited hours into the penalty variable (Pitfall 3).
                over = self.m.NewIntVar(
                    0, max(0, hard_cap_scaled - scaled_max), f"maxh_over_{mid[:6]}"
                )
                total = sum(int(round(sv.eff_h * C.VOL_SCALE)) * sv.var for sv in member_svs)
                self.m.Add(total <= scaled_max + over)
                maxh_terms.append(over)
            # scale_demand is handled in _aggregate_demand, not here (D-10)

        self.round2_cost = (
            sum(cost_terms)
            + C.MIN_WORKERS_PENALTY * sum(shortfall_terms)
            + C.LOCK_SHIFT_PENALTY * sum(lock_terms)
            + C.EXCLUDE_WORKER_PENALTY * sum(excl_terms)
            # `over` (built above) is VOL_SCALE-scaled (hundredths-of-an-hour), unlike the
            # other three penalty terms which sum unscaled headcount/bool vars already in
            # cents-space — divide VOL_SCALE back out here or this term inflates ~100x.
            + (C.MAX_HOURS_PENALTY // C.VOL_SCALE) * sum(maxh_terms)
            if (cost_terms or shortfall_terms or lock_terms or excl_terms or maxh_terms)
            else 0
        )
