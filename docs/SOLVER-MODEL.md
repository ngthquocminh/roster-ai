# Solver Model

How a scenario fixture becomes a CP-SAT model, and what that model keeps from the production scheduler it distills. The code is `backend/ingest/input_adapter.py` (fixture → domain), `backend/domain/` (pure types), and `backend/engine/cpsat/` (builder, lexicographic objective, engine). The governed path reaches it only through `backend/engine/governed_adapter.py`; demand family and unit rules are normative in [`DOMAIN-MODEL.md`](DOMAIN-MODEL.md).

## Data pipeline

**Demand source decision:** consume the **materialized `Outbound Workload` /
`Inbound Workload` / `Indirect Workforce Requirement`** tables that already exist
in the sample. We do **not** reproduce the production adapter's
`Order Volume → Workload` generation (site-flow splits, conversions,
dispatch-readiness caps — hundreds of lines, out of scope).

**Fixture tool** (`fixtures/build_short_input.py`):
- **Shrink vertically, keep the whole week.** Span the full Scenario Range (no
  day truncation) — so coverage reports cover all seven days. (`HORIZON_DAYS` can
  truncate for a quick probe, but defaults to the full week.)
- Select top-demand tasks per family **that have coherent supply** (≥1 qualified
  member rostered/available in the horizon) — never keep a starved task.
- Greedily pull in qualified+rostered members (cap total) so every kept task is
  serviceable; deliberately undersupply to keep some unmet interesting.
- **Scale demand to the kept workforce's real capacity:** sum each kept member's
  actual roster-window hours over the week (capped at the weekly limit) and scale
  OB/IB volume to `DEMAND_LOAD ×` that, so coverage lands in an informative band
  rather than ~2% (or an inflated 100%).
- **Retain & hourly-aggregate** Outbound Workload (14-min → hourly bands;
  lossless for hourly coverage); prune Inbound `Tasks[]` to kept tasks.
- Emit the **same real schema**, just tiny (current output: ~410 KB, 11 members,
  6 tasks across 3 families, full 7-day week).

> Design note: an alternative shrink strategy does stratified member sampling +
> demand-coverage top-up but drops the materialized Workload and regenerates it
> from Order Volume — the opposite of our "consume Workload" decision. We borrow
> the coverage-top-up idea, not the Workload-drop behaviour.

**Input adapter** (`ingest/input_adapter.py`): real-schema JSON → `SchedulingProblem`.

| Output | Built from |
|---|---|
| time axis (hours 0..168) | `Scenario Range.PeriodStartDate`; all datetimes → hours-from-start |
| `Member` | `Team Member` (emp type, grade, EBA, contracted hours) |
| rosters / availability | `Roster Profile`, `Availability` (windows → hour offsets) |
| qualification + rate | `Team Member Qualification and Performance` (`TeamMemberTaskRateOverride` ?? `DefaultTaskRate`) |
| wage $/hr | `EBA Grade Rate` where `RateType == "Base Rate"`, keyed (EBAID, GradeID) |
| `Task` (function/area/unit) | `Task` + `Function` |
| outbound/inbound demand bands | `Outbound Workload`, `Inbound Workload` (per task, window, volume) |
| indirect headcount bands | `Indirect Workforce Requirement` (window + `RequiredHeadcount`) |
| shift templates + breaks | `Shift Schedule Template` + `Shift Schedule Template Break` |

## Domain types (`domain/`)

Pure dataclasses/namedtuples, no solver imports. Time is **hours from scenario
start** (e.g. day-1 17:30 = `17.5`, day-2 06:00 = `30.0`).

```
Member(contact_id, emp_type, grade_id, eba_id, contracted_hours,
       rosters: list[Window], availabilities: list[Window],
       qualifications: list[Qual])              # Qual(task_id, rate, preferred)
Task(task_id, name, function, area_id, unit_id)
ShiftTemplate(id, length_h, breaks: list[Break])  # Break(start_offset, dur, paid)
OutboundDemand(task_id, start_h, end_h, volume)   # units
InboundDemand(task_id, order_id, start_h, end_h, volume)
IndirectDemand(task_id, start_h, end_h, headcount)
SchedulingProblem(horizon_h, members, tasks, templates,
                  outbound, inbound, indirect, wage_by_member, rate_by_member_task)
```

`SolveResult(status, objective_terms, schedule: list[ScheduleRow], metrics: SummaryMetrics)`
where `ScheduleRow(member, task, start_h, end_h, shift_id)` and `SummaryMetrics`
mirrors the existing spec (per-function coverage %, coverage by day, cost,
solver stats).

## The model (CP-SAT)

**Time/units.** Work in **integer minutes** for time; scale **volume/rate ×100**
into integers (CP-SAT is integer-only). One coverage bucket per integer hour.

**Decision variables**
- `shift[m, period, template, start]` ∈ {0,1} — a candidate shift for member `m`
  generated from a roster/availability window, of a template, starting at `start`.
  Generated only within the window; breaks come from the template → working
  segments.
- `task[m, shift, task_id, slot]` ∈ {0,1} — member does `task_id` during a working
  slot of a selected shift. Shift split into 1–2 slots by length
  (`≤6h→1`, `>6h→2`), per the real model's `get_task_segment_count`.
- `unmet_ob[task,h]`, `unmet_ib[task,h]` (scaled int ≥0), `unmet_ind[task,h]`
  (int ≥0) — coverage shortfall per task-hour.
- `unfilled_roster[period]` ∈ {0,1} — soft roster non-fill.

**Constraints (the distilled core)**
1. **Shift↔task link:** `task ≤ shift`; a selected shift carries ≥1 task; no two
   tasks overlap within a shift.
2. **Roster fill:** for each roster window, `Σ shift + unfilled_roster == 1`
   (soft — keeps the model feasible).
3. **Coverage (per task, per hour `h`):**
   - OB/IB: `Σ task.selected · rate(m,task) · overlap(task,h) · absenteeism + unmet[task,h] ≥ demand_volume(task,h)`
   - IND: `Σ task.selected (headcount) + unmet_ind[task,h] ≥ required_headcount(task,h)`
   where `demand_volume(task,h)` = band volume pro-rated to hour `h`,
   `absenteeism = 100/110` (flat 10%, from the real model).
4. **Qualification gate:** `task[m,_,task_id,_]` vars are only generated for
   `(m, task_id)` the member is qualified for (rate present).
5. **Hour/shift caps** (per employment type, defaults from constants):
   weekly effective-hours ≤ cap; ≤ max shifts/day & /week; min gap between shifts;
   (max consecutive days — optional).

**Objective — lexicographic** (CP-SAT has no native lex → *solve-and-lock*:
solve round 1, add `obj1 ≤ best1 + ε`, solve round 2, …):
1. `min Σ unmet_hours` (OB/IB unmet ÷ rate + IND unmet · duration; + small
   `unfilled_roster` weight).
2. `min cost` = `Σ shift.selected · effective_hours · wage($/hr)`.

*(A middle "workforce-quality" round — preference/emp-type priority — is a
documented extension point, currently off.)*

**Engine seam** (`engine/base.py`)
```
class SchedulerEngine(Protocol):
    def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult: ...
SolverConfig(time_limit_s=30.0, num_workers=8, seed=42, overrides=[])  # overrides: soft round-2 penalties
create_engine(name) -> SchedulerEngine     # {"cpsat": CpSatEngine}
```
Switching engines later = add `engine/<x>/` + a registry entry; domain/adapter
untouched.

## Distilled scope vs. the production model

| Kept | Deferred (future `enable_*` toggles) |
|---|---|
| Shift generation from rosters/availability + templates w/ breaks | Task flow (inbound OrderFlow chaining) |
| shift + task binaries, one-task-per-slot | Staging / floor / storage capacity, load management |
| Hourly coverage + unmet, all 3 families | Freezer warm-up breaks, productivity bands |
| One-shift-per-roster (soft) | Rotation rules, fair share, preferred OT/area, equipment caps |
| Weekly-hours + max-shifts/day + min-gap caps | Daily re-opt, fixed/published shifts |
| Lex objective: unmet → cost | Full OT1/OT2 day+week envelope (→ flat $/hr now) |
| Qualification gate | EBA grade-rate tables (→ single Base Rate now) |
| | The Phase-2A/B/C task-spec budget/hour-cap filtering |

