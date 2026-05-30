"""
build_short_input.py — Extract a small, *referentially coherent* slice of the
full weekly input so the Scheduling Engine solves in seconds.

The slice is shrunk **vertically**, not horizontally: we keep the **whole week**
(the full Scenario Range) and instead cut the problem down by (a) keeping only a
handful of tasks per demand family, (b) keeping only the qualified+rostered
members that supply those tasks, and (c) scaling demand volume so required hours
stay near DEMAND_LOAD x the kept workforce's weekly capacity. This mirrors the
production dev tool (scripts/dev/make_short_input.py), which subsamples members
and demand but never truncates the horizon — so the coverage report spans all
seven days rather than only the first two.

"Coherent" means: every demand task we keep is qualified-for and rostered-over by
at least one member we keep. Otherwise the tiny instance would be trivially 100%
unmet (no supply can reach the demand) and tell us nothing.

Output keeps the *same table names/field names* as the real input (a strict
subset), so the engine's adapter reads the real schema — just tiny.

Run:
    python fixtures/build_short_input.py
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timedelta

# --------------------------------------------------------------------------
# Config — tune the size of the tiny instance here
# --------------------------------------------------------------------------
SRC = r"data\sample_weekly_input.json"
# repo-root/data/ (this file lives at repo-root/backend/fixtures/)
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DST = os.path.join(_REPO_ROOT, "data", "sample_tiny_input.json")

# Horizon: keep the WHOLE scenario week. Set HORIZON_DAYS to an int to truncate
# (horizontal shrink); leave it None to span the full Scenario Range so the
# coverage report covers every day. We shrink the instance vertically instead
# (fewer tasks/members + demand scaling), so there's no need to cut days.
HORIZON_DAYS = None       # None => full scenario range; int => first N days only
N_OUTBOUND_TASKS = 3      # top-volume outbound tasks to keep
N_INBOUND_TASKS = 2       # top-volume inbound tasks to keep
N_INDIRECT_TASKS = 2      # indirect tasks to keep
MAX_MEMBERS = 14          # hard cap on members in the slice
MEMBERS_PER_TASK = 3      # qualified+rostered members to pull in per kept task
DEMAND_LOAD = 1.3         # scale OB/IB demand so required hours ~= this x supply
                          # capacity (>1 => meaningful-but-not-trivial unmet)

DT_FMT = "%Y-%m-%dT%H:%M:%S"


def parse_dt(s: str) -> datetime:
    return datetime.strptime(s.split(".")[0], DT_FMT)


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def main() -> None:
    d = load(SRC)

    # ---- scenario horizon ----
    rng = d["Scenario Range"][0]
    start = parse_dt(rng["PeriodStartDate"])
    if HORIZON_DAYS is None:
        # Full week: span the whole Scenario Range (vertical shrink only).
        horizon_end = parse_dt(rng["PeriodEndDate"])
    else:
        horizon_end = start + timedelta(days=HORIZON_DAYS)
    horizon_days = max(1.0, (horizon_end - start).total_seconds() / 86400.0)

    def in_horizon(dt: datetime) -> bool:
        return start <= dt < horizon_end

    def hours_off(dt: datetime) -> float:
        return (dt - start).total_seconds() / 3600.0

    # ---- task metadata indexes ----
    func_name = {f["FunctionID"]: f["Name"] for f in d.get("Function", [])}
    task_by_id = {t["TaskID"]: t for t in d.get("Task", []) if t.get("TaskID")}

    def task_func(tid: str) -> str:
        t = task_by_id.get(tid)
        return func_name.get(t["FunctionID"], "Unknown") if t else "Unknown"

    # ----------------------------------------------------------------------
    # 1) Collect in-horizon demand volume per task, per family
    # ----------------------------------------------------------------------
    ob_vol = defaultdict(float)
    for w in d.get("Outbound Workload", []):
        try:
            s, e = parse_dt(w["StartDateTime"]), parse_dt(w["EndDateTime"])
        except Exception:
            continue
        if in_horizon(s) and float(w.get("Volume") or 0) > 0:
            ob_vol[w["TaskID"]] += float(w["Volume"])

    ib_vol = defaultdict(float)
    for w in d.get("Inbound Workload", []):
        try:
            s = parse_dt(w["WindowStartDateTime"])
        except Exception:
            continue
        if not in_horizon(s):
            continue
        for tk in w.get("Tasks", []):
            if float(tk.get("Volume") or 0) > 0:
                ib_vol[tk["TaskID"]] += float(tk["Volume"])

    ind_hc = defaultdict(float)
    for w in d.get("Indirect Workforce Requirement", []):
        try:
            day = parse_dt(w["Date"])
        except Exception:
            continue
        if not (start <= day < horizon_end):
            continue
        if float(w.get("RequiredHeadcount") or 0) > 0:
            ind_hc[w["TaskID"]] += float(w["RequiredHeadcount"])

    # ----------------------------------------------------------------------
    # 2) Member windows + qualifications (need these to test "has supply")
    # ----------------------------------------------------------------------
    def windows_for(table: str):
        by_cid = defaultdict(list)
        for r in d.get(table, []):
            try:
                s, e = parse_dt(r["StartDateTime"]), parse_dt(r["EndDateTime"])
            except Exception:
                continue
            if s < horizon_end and e > start:   # overlaps horizon
                by_cid[r["ContactID"]].append(r)
        return by_cid

    rosters_by_cid = windows_for("Roster Profile")
    avail_by_cid = windows_for("Availability")
    scheduled_cids = set(rosters_by_cid) | set(avail_by_cid)

    # qualification index across ALL demand tasks (for supply tests + selection)
    all_demand_tasks = set(ob_vol) | set(ib_vol) | set(ind_hc)
    all_demand_tasks.discard(None)
    qual_by_task = defaultdict(list)  # task_id -> [(contactid, rate)]
    for q in d.get("Team Member Qualification and Performance", []):
        tid = q.get("TaskID")
        if tid in all_demand_tasks:
            rate = q.get("TeamMemberTaskRateOverride") or q.get("DefaultTaskRate") or 0
            qual_by_task[tid].append((q["ContactID"], float(rate)))

    def supply_candidates(tid):
        """Qualified members rostered/available in horizon with a positive rate."""
        return [
            (cid, rate) for cid, rate in qual_by_task.get(tid, [])
            if cid in scheduled_cids and rate > 0
        ]

    # ----------------------------------------------------------------------
    # 3) Pick tasks per family — only tasks that actually have supply, one
    #    family each, highest demand first.
    # ----------------------------------------------------------------------
    fam_of: dict = {}
    keep_tasks: set = set()

    def pick(vol_map, n, fam):
        ranked = sorted((t for t in vol_map if supply_candidates(t)),
                        key=lambda t: -vol_map[t])
        taken = 0
        for t in ranked:
            if t in keep_tasks:
                continue
            keep_tasks.add(t)
            fam_of[t] = fam
            taken += 1
            if taken >= n:
                break

    pick(ob_vol, N_OUTBOUND_TASKS, "OB")
    pick(ib_vol, N_INBOUND_TASKS, "IB")
    pick(ind_hc, N_INDIRECT_TASKS, "IND")

    # ----------------------------------------------------------------------
    # 4) Gather members so every kept task has supply (cap total members)
    # ----------------------------------------------------------------------
    keep_members: set = set()
    task_covered: dict = {}
    for tid in sorted(keep_tasks, key=lambda t: -(ob_vol[t] + ib_vol[t] + ind_hc[t])):
        cands = supply_candidates(tid)
        cands.sort(key=lambda cr: (cr[0] not in rosters_by_cid, -cr[1]))  # rostered first, faster first
        chosen = [cid for cid, _ in cands[:MEMBERS_PER_TASK]]
        # always keep at least one supplier even if over the cap, so no kept task is starved
        for cid in chosen:
            if len(keep_members) < MAX_MEMBERS or cid in keep_members or not task_covered.get(tid):
                keep_members.add(cid)
                task_covered[tid] = True

    # ----------------------------------------------------------------------
    # 4) Emit the tiny instance (same schema, filtered)
    # ----------------------------------------------------------------------
    members = [m for m in d.get("Team Member", []) if m["ContactID"] in keep_members]
    used_eba = {m["EBAID"] for m in members}
    used_grade = {m["GradeID"] for m in members}
    used_emp = {m["EmploymentTypeID"] for m in members}
    used_area = {task_by_id[t]["AreaID"] for t in keep_tasks if t in task_by_id}
    used_unit = {task_by_id[t].get("UnitTypeID") for t in keep_tasks if t in task_by_id}
    used_func = {task_by_id[t]["FunctionID"] for t in keep_tasks if t in task_by_id}

    def filt(table, pred):
        return [r for r in d.get(table, []) if pred(r)]

    # keep a few short shift templates so shift generation is cheap
    # Keep a *spread* of shift lengths (not the 4 shortest) so the model can use
    # longer shifts; shifts > 6h get 2 task slots, materially raising throughput.
    by_tpl_id = {}
    for t in d.get("Shift Schedule Template", []):
        h = float(t.get("TotalShiftHours") or 0)
        tid = t.get("ShiftScheduleTemplateID")
        if 0 < h <= 11 and tid not in by_tpl_id:
            by_tpl_id[tid] = t
    avail_tpls = list(by_tpl_id.values())
    kept_tpl = []
    for target in (4.0, 6.0, 8.0, 10.0):
        if not avail_tpls:
            break
        best = min(avail_tpls, key=lambda t: abs(float(t["TotalShiftHours"]) - target))
        kept_tpl.append(best)
        avail_tpls.remove(best)
    kept_tpl_ids = {t["ShiftScheduleTemplateID"] for t in kept_tpl}

    # Demand scaling: the kept top-volume tasks dwarf a 12-member workforce, so
    # without scaling coverage is ~2% and uninformative. Scale OB/IB volumes so
    # total required labour-hours ~= DEMAND_LOAD x available supply capacity.
    ref_rate = {}
    for tid in keep_tasks:
        rates = [r for cid, r in qual_by_task.get(tid, []) if cid in keep_members and r > 0]
        ref_rate[tid] = (sum(rates) / len(rates)) if rates else 100.0
    required_h = sum(ob_vol[t] / ref_rate[t] for t in keep_tasks if ob_vol.get(t)) \
        + sum(ib_vol[t] / ref_rate[t] for t in keep_tasks if ib_vol.get(t))
    # ~one 8h shift/member/day, capped at the weekly-hours limit (56h).
    capacity_h = max(1.0, len(keep_members) * min(horizon_days * 8.0, 56.0))
    demand_scale = min(1.0, capacity_h * DEMAND_LOAD / required_h) if required_h > 0 else 1.0

    # Outbound: aggregate the fine-grained (14-min) bands into hourly bands per
    # (task, area). The engine buckets coverage by integer hour, so this is
    # lossless for it and collapses ~1500 rows to a few dozen.
    ob_hourly = defaultdict(float)  # (task_id, area_id, hour_bucket_start_iso, end_iso) -> volume
    for w in d.get("Outbound Workload", []):
        if w.get("TaskID") not in keep_tasks:
            continue
        try:
            s = parse_dt(w["StartDateTime"])
        except Exception:
            continue
        if not in_horizon(s):
            continue
        bucket = s.replace(minute=0, second=0, microsecond=0)
        key = (w["TaskID"], w.get("AreaID"),
               bucket.strftime(DT_FMT), (bucket + timedelta(hours=1)).strftime(DT_FMT))
        ob_hourly[key] += float(w.get("Volume") or 0) * demand_scale
    ob_rows = [
        {"StartDateTime": s, "EndDateTime": e, "AreaID": area, "TaskID": tid, "Volume": round(v, 4)}
        for (tid, area, s, e), v in sorted(ob_hourly.items()) if v > 0
    ]

    # Inbound: keep in-horizon rows, but prune each row's nested Tasks[] to the
    # kept tasks only (the raw rows carry the full task chain → most of the bytes).
    ib_rows = []
    for w in d.get("Inbound Workload", []):
        try:
            s = parse_dt(w["WindowStartDateTime"])
        except Exception:
            continue
        if not in_horizon(s):
            continue
        kept = [{**tk, "Volume": round(float(tk.get("Volume") or 0) * demand_scale, 4)}
                for tk in w.get("Tasks", []) if tk["TaskID"] in keep_tasks]
        if not kept:
            continue
        ib_rows.append({**w, "Tasks": kept})

    def ind_keep(w):
        try:
            day = parse_dt(w["Date"])
        except Exception:
            return False
        return start <= day < horizon_end and w["TaskID"] in keep_tasks

    tiny = {
        "Scenario Range": [{"PeriodStartDate": rng["PeriodStartDate"],
                            "PeriodEndDate": horizon_end.strftime(DT_FMT)}],  # full week when HORIZON_DAYS is None
        "Settings": d.get("Settings", []),
        "Function": [f for f in d.get("Function", []) if f["FunctionID"] in used_func],
        "Area": [a for a in d.get("Area", []) if a["AreaID"] in used_area],
        "Unit Type": [u for u in d.get("Unit Type", []) if u["UnitTypeID"] in used_unit],
        "Employment Type": [e for e in d.get("Employment Type", []) if e["EmploymentTypeID"] in used_emp],
        "EBA": [e for e in d.get("EBA", []) if e["EBAID"] in used_eba],
        "Grade": [g for g in d.get("Grade", []) if g["GradeID"] in used_grade],
        "Rate Type": d.get("Rate Type", []),
        "EBA Grade Rate": filt("EBA Grade Rate", lambda r: r["EBAID"] in used_eba and r["GradeID"] in used_grade),
        "Shift Constraint": d.get("Shift Constraint", []),
        "Shift Schedule Template": kept_tpl,
        "Shift Schedule Template Break": filt(
            "Shift Schedule Template Break",
            lambda b: b.get("ShiftScheduleTemplateID") in kept_tpl_ids,
        ),
        "Task": [task_by_id[t] for t in keep_tasks if t in task_by_id],
        "Team Member": members,
        "Team Member Qualification and Performance": filt(
            "Team Member Qualification and Performance",
            lambda q: q["ContactID"] in keep_members and q["TaskID"] in keep_tasks,
        ),
        "Roster Profile": filt("Roster Profile", lambda r: r["ContactID"] in keep_members
                               and r["ContactID"] in rosters_by_cid),
        "Availability": filt("Availability", lambda r: r["ContactID"] in keep_members
                             and r["ContactID"] in avail_by_cid),
        "Outbound Workload": ob_rows,
        "Inbound Workload": ib_rows,
        "Indirect Workforce Requirement": filt("Indirect Workforce Requirement", ind_keep),
    }

    os.makedirs(os.path.dirname(DST), exist_ok=True)
    with open(DST, "w", encoding="utf-8") as fh:
        json.dump(tiny, fh, indent=1)

    # ---- report ----
    size_kb = os.path.getsize(DST) / 1024
    print(f"Wrote {DST}  ({size_kb:.0f} KB)")
    print(f"Horizon: {start.date()} -> {horizon_end.date()} ({horizon_days:.0f}d, "
          f"{'full week' if HORIZON_DAYS is None else f'{HORIZON_DAYS}d truncated'})")
    print(f"Members kept: {len(members)}")
    print(f"Tasks kept:   {len(tiny['Task'])}  "
          f"(OB={N_OUTBOUND_TASKS} IB={N_INBOUND_TASKS} IND={N_INDIRECT_TASKS} requested)")
    for tid in sorted(keep_tasks, key=lambda t: fam_of[t]):
        fam = fam_of[tid]
        vol = ob_vol[tid] if fam == "OB" else ib_vol[tid] if fam == "IB" else ind_hc[tid]
        nsup = sum(1 for cid, r in qual_by_task.get(tid, []) if cid in keep_members and r > 0)
        flag = "" if task_covered.get(tid) else "  <-- NO SUPPLY"
        print(f"  [{fam:3}] {task_func(tid):14} vol/hc={vol:9.1f}  qualified-members-kept={nsup}{flag}")
    print(f"Outbound rows: {len(tiny['Outbound Workload'])}, "
          f"Inbound rows: {len(tiny['Inbound Workload'])}, "
          f"Indirect rows: {len(tiny['Indirect Workforce Requirement'])}")
    print(f"Roster rows: {len(tiny['Roster Profile'])}, "
          f"Availability rows: {len(tiny['Availability'])}, "
          f"Shift templates: {len(kept_tpl)}")


if __name__ == "__main__":
    main()
