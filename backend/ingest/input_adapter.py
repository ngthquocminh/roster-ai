"""Adapter: real-schema weekly JSON -> pure-domain SchedulingProblem.

Consumes the materialized `Outbound Workload` / `Inbound Workload` /
`Indirect Workforce Requirement` tables (we do NOT regenerate demand from
Order Volume — see design.md). Everything is clipped to the scenario horizon.
"""
from __future__ import annotations

import json
from collections import defaultdict
from typing import Any, Dict, List

from domain.problem import SchedulingProblem
from domain.types import (
    Break,
    DemandBand,
    DemandFamily,
    Member,
    Qualification,
    ShiftTemplate,
    Task,
    Window,
    WindowKind,
)
from ingest.scenario_time import day_window_hours, hours_from, parse_dt, parse_time_of_day


def _rows(data: dict, key: str) -> List[dict]:
    v = data.get(key, [])
    return v if isinstance(v, list) else []


def _to_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _clip(s: float, e: float, lo: float, hi: float) -> tuple[float, float] | None:
    s, e = max(s, lo), min(e, hi)
    return (s, e) if e > s else None


def load_problem(path: str) -> SchedulingProblem:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return build_problem(data)


def build_problem(data: dict) -> SchedulingProblem:
    rng = _rows(data, "Scenario Range")[0]
    start = parse_dt(rng["PeriodStartDate"])
    horizon_h = hours_from(start, parse_dt(rng["PeriodEndDate"]))

    # ---- tasks ----
    func_name = {f["FunctionID"]: f.get("Name", "Unknown") for f in _rows(data, "Function")}
    tasks: List[Task] = []
    task_ids: set = set()
    for t in _rows(data, "Task"):
        tid = t.get("TaskID")
        if not tid or tid in task_ids:
            continue
        task_ids.add(tid)
        tasks.append(Task(
            task_id=tid,
            name=t.get("Task", ""),
            function=func_name.get(t.get("FunctionID"), "Unknown"),
            area_id=t.get("AreaID", ""),
            unit_id=t.get("UnitTypeID"),
        ))

    # ---- wages: EBA Grade Rate (Base Rate) keyed (EBAID, GradeID) ----
    wage_by_eba_grade: Dict[tuple, float] = {}
    base_rates: List[float] = []
    for r in _rows(data, "EBA Grade Rate"):
        if str(r.get("RateType", "")).strip().lower() != "base rate":
            continue
        amt = _to_float(r.get("Amount"))
        wage_by_eba_grade[(r.get("EBAID"), r.get("GradeID"))] = amt
        base_rates.append(amt)
    default_wage = (sum(base_rates) / len(base_rates)) if base_rates else 40.0

    # ---- member windows ----
    def windows_for(table: str, kind: WindowKind) -> Dict[str, List[Window]]:
        by_cid: Dict[str, List[Window]] = defaultdict(list)
        for i, r in enumerate(_rows(data, table)):
            try:
                s = hours_from(start, parse_dt(r["StartDateTime"]))
                e = hours_from(start, parse_dt(r["EndDateTime"]))
            except Exception:
                continue
            clipped = _clip(s, e, 0.0, horizon_h)
            if clipped is None:
                continue
            cid = r["ContactID"]
            by_cid[cid].append(Window(id=f"{kind.value[:3]}{i}", start_h=clipped[0],
                                       end_h=clipped[1], kind=kind))
        return by_cid

    rosters = windows_for("Roster Profile", WindowKind.ROSTER)
    avails = windows_for("Availability", WindowKind.AVAILABILITY)

    # ---- qualifications + rates per member ----
    quals_by_cid: Dict[str, List[Qualification]] = defaultdict(list)
    for q in _rows(data, "Team Member Qualification and Performance"):
        tid = q.get("TaskID")
        if tid not in task_ids:
            continue
        rate = _to_float(q.get("TeamMemberTaskRateOverride") or q.get("DefaultTaskRate"))
        if rate <= 0:
            continue
        quals_by_cid[q["ContactID"]].append(Qualification(task_id=tid, rate=rate))

    # ---- members ----
    members: List[Member] = []
    for m in _rows(data, "Team Member"):
        cid = m["ContactID"]
        wage = wage_by_eba_grade.get((m.get("EBAID"), m.get("GradeID")), default_wage)
        win = rosters.get(cid, []) + avails.get(cid, [])
        quals = quals_by_cid.get(cid, [])
        if not win or not quals:
            continue  # cannot be scheduled or has nothing to do
        members.append(Member(
            contact_id=cid,
            name=m.get("Team Member", "Unknown"),
            emp_type=m.get("EmploymentType", "Unknown"),
            grade_id=m.get("GradeID", ""),
            eba_id=m.get("EBAID", ""),
            contracted_hours=_to_float(m.get("ContractedHours"), 38.0),
            wage_per_hour=wage,
            windows=win,
            qualifications=quals,
        ))

    # ---- demand ----
    demand: List[DemandBand] = []

    for i, w in enumerate(_rows(data, "Outbound Workload")):
        tid = w.get("TaskID")
        vol = _to_float(w.get("Volume"))
        if tid not in task_ids or vol <= 0:
            continue
        try:
            s = hours_from(start, parse_dt(w["StartDateTime"]))
            e = hours_from(start, parse_dt(w["EndDateTime"]))
        except Exception:
            continue
        clipped = _clip(s, e, 0.0, horizon_h)
        if clipped:
            demand.append(DemandBand(tid, DemandFamily.OUTBOUND, clipped[0], clipped[1],
                                     vol, order_id=f"OB{i}"))

    for i, w in enumerate(_rows(data, "Inbound Workload")):
        try:
            s = hours_from(start, parse_dt(w["WindowStartDateTime"]))
            e = hours_from(start, parse_dt(w["WindowEndDateTime"]))
        except Exception:
            continue
        clipped = _clip(s, e, 0.0, horizon_h)
        if not clipped:
            continue
        for tk in w.get("Tasks", []):
            tid = tk.get("TaskID")
            vol = _to_float(tk.get("Volume"))
            if tid in task_ids and vol > 0:
                demand.append(DemandBand(tid, DemandFamily.INBOUND, clipped[0], clipped[1],
                                         vol, order_id=f"IB{i}"))

    for i, w in enumerate(_rows(data, "Indirect Workforce Requirement")):
        tid = w.get("TaskID")
        hc = _to_float(w.get("RequiredHeadcount"))
        if tid not in task_ids or hc <= 0:
            continue
        try:
            s, e = day_window_hours(start, w["Date"], w["WindowStartDateTime"], w["WindowEndDateTime"])
        except Exception:
            continue
        clipped = _clip(s, e, 0.0, horizon_h)
        if clipped:
            demand.append(DemandBand(tid, DemandFamily.INDIRECT, clipped[0], clipped[1],
                                     hc, order_id=f"IND{i}"))

    # ---- shift templates (dedupe by ShiftScheduleTemplateID) ----
    breaks_by_tpl: Dict[str, List[Break]] = defaultdict(list)
    for b in _rows(data, "Shift Schedule Template Break"):
        tpl = b.get("ShiftScheduleTemplateID")
        breaks_by_tpl[tpl].append(Break(
            start_offset_h=parse_time_of_day(b.get("StartHour", "00:00:00")),
            duration_h=_to_float(b.get("Minutes")) / 60.0,
            paid=bool(b.get("IsPaid")),
        ))
    templates: List[ShiftTemplate] = []
    seen_tpl: set = set()
    for t in _rows(data, "Shift Schedule Template"):
        tpl = t.get("ShiftScheduleTemplateID")
        length = _to_float(t.get("TotalShiftHours"))
        if not tpl or tpl in seen_tpl or length <= 0:
            continue
        seen_tpl.add(tpl)
        templates.append(ShiftTemplate(
            id=tpl,
            name=t.get("Name", tpl[:8]),
            length_h=length,
            breaks=tuple(sorted(breaks_by_tpl.get(tpl, []), key=lambda b: b.start_offset_h)),
        ))

    return SchedulingProblem(
        horizon_h=horizon_h,
        members=members,
        tasks=tasks,
        templates=templates,
        demand=demand,
    )
