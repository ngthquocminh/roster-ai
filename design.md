# NL Workforce Scheduling Assistant — System Design

**What it is.** A workforce scheduling assistant: load a distribution-centre week of
workforce + demand data → a constraint solver produces a weekly schedule →
(later) describe constraint tweaks in plain English and have an LLM explain the
result. The **Scheduling Engine** is an open-source-solver (OR-Tools CP-SAT)
reimplementation of the core logic of the production MDC model
(CPLEX/docplex, ~2,500 lines of constraints, ~759 team members).

**Status.** This document is the working spec. **Phase 1 (Scheduling Engine +
data spine)** is the current build target; the rest of the system is described
for context and to keep the architecture honest.

---

## 1. Naming & terminology

| Term | Meaning |
|---|---|
| **Scheduling Engine** | The optimization model + solver. Distilled from the weekly model. |
| **Fixture / short input** | A small, coherent slice of a full weekly input, for fast iteration. |
| **Scenario** | A named workspace: one input dataset + constraint overrides. |
| **Run** | One solve of a scenario snapshot → schedule + metrics. |
| **Engine adapter** | Real-schema JSON → pure-domain `SchedulingProblem`. |

---

## 2. Whole-system architecture (target)

Dependencies point inward; the domain never imports infrastructure.

```
React UI  ──HTTP──▶  FastAPI routers
                         │
                      Services (use-cases)
              ┌──────────┴───────────────┐
       Scheduling Engine             LLM providers
   (SchedulerEngine Protocol)    (LLMProvider Protocol)
       CP-SAT now; PuLP/CPLEX     Claude now; Gemini later
       later                          │
              │                       │
        Domain types (pure Python, zero solver/web deps)
              ▲
   Infrastructure: input adapter, fixture tool, SQLite repos
```

The two **Protocol seams** (engine, LLM) are the extensibility guarantee:
swapping the solver library or LLM vendor touches only one infra package.

**Phase map**
1. **Engine + data spine** ← *current.* Fixture tool → adapter → domain → CP-SAT engine → CLI run on a short input. No web, no LLM.
2. Backend skeleton: SQLite + sessions/scenarios/fixtures + threaded run execution + results endpoints.
3. LLM: NL constraint parser (soft overrides) + insight generator, wired into runs.
4. Frontend: results, constraints, run flow.
5. What-if + delta explanation, polish, deploy.

---

## 3. Phase 1 — Scheduling Engine + data spine

### 3.1 Repository layout (Phase 1)

```
nl-scheduling-assistant/            # one git repo
  data/
    sample_tiny_input.json          # generated fixture (committed, shared)
  backend/                          # Phase 1 lives here; FastAPI app added in Phase 2
    fixtures/
      build_short_input.py          # full weekly JSON -> small coherent fixture
    engine/
      base.py                       # SchedulerEngine Protocol, SolverConfig, factory
      cpsat/
        builder.py                  # SchedulingProblem -> CP-SAT vars + constraints
        objective.py                # lexicographic solve-and-lock rounds
        engine.py                   # CpSatEngine implements SchedulerEngine
    domain/
      types.py                      # Member, Task, Demand*, ShiftTemplate, Roster, Qualification
      problem.py                    # SchedulingProblem (engine input)
      result.py                     # SolveResult, ScheduleRow, SummaryMetrics
    io/
      input_adapter.py              # real-schema JSON -> SchedulingProblem
      scenario_time.py              # datetime <-> hours-from-start helpers
    config/
      constants.py                  # distilled constants (caps, rates, segment rules)
    run.py                          # load fixture -> solve -> print metrics
    tests/
      test_adapter.py test_engine_small.py
    requirements.txt
  frontend/                         # added in Phase 4
  design.md  docker-compose.yml  README.md
```

Deployment target is **AWS** (not yet planned in detail): frontend → S3 +
CloudFront; backend container → ECR + App Runner/ECS/EC2 (container compute, not
Lambda — the CP-SAT solve is CPU-heavy and long-running); SQLite on EFS or RDS
later. The monorepo deploys per-subdir via path-filtered CI.

### 3.2 Data pipeline

**Demand source decision:** consume the **materialized `Outbound Workload` /
`Inbound Workload` / `Indirect Workforce Requirement`** tables that already exist
in the sample. We do **not** reproduce the production adapter's
`Order Volume → Workload` generation (site-flow splits, conversions,
dispatch-readiness caps — hundreds of lines, out of scope).

**Fixture tool** (`fixtures/build_short_input.py`, evolved from the prototype
`scripts/shrink_input.py`):
- Pick a horizon (default 2 days from scenario start).
- Select top-demand tasks per family **that have coherent supply** (≥1 qualified
  member rostered/available in the horizon) — never keep a starved task.
- Greedily pull in qualified+rostered members (cap total) so every kept task is
  serviceable; deliberately undersupply to keep some unmet interesting.
- **Retain & hourly-aggregate** Outbound Workload (14-min → hourly bands;
  lossless for hourly coverage); prune Inbound `Tasks[]` to kept tasks.
- Emit the **same real schema**, just tiny (current output: ~180 KB, 12 members,
  6 tasks across 3 families, 2-day horizon).

> Reference: the production `scripts/dev/make_short_input.py` does robust
> stratified member sampling + demand-coverage top-up, but is built around
> dropping Workload and regenerating from Order Volume — the opposite of our
> "consume Workload" decision. We borrow its coverage-top-up idea, not its
> Workload-drop behaviour.

**Input adapter** (`io/input_adapter.py`): real-schema JSON → `SchedulingProblem`.

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

### 3.3 Domain types (`domain/`)

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

### 3.4 The model (CP-SAT)

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
   (max consecutive days — optional in Phase 1).

**Objective — lexicographic** (CP-SAT has no native lex → *solve-and-lock*:
solve round 1, add `obj1 ≤ best1 + ε`, solve round 2, …):
1. `min Σ unmet_hours` (OB/IB unmet ÷ rate + IND unmet · duration; + small
   `unfilled_roster` weight).
2. `min cost` = `Σ shift.selected · effective_hours · wage($/hr)`.

*(A middle "workforce-quality" round — preference/emp-type priority — is a
documented extension point, off in Phase 1.)*

**Engine seam** (`engine/base.py`)
```
class SchedulerEngine(Protocol):
    def solve(self, problem: SchedulingProblem, config: SolverConfig) -> SolveResult: ...
SolverConfig(time_limit_s=60, rel_gap=0.0, scale=100, num_workers=8)
create_engine(name) -> SchedulerEngine     # {"cpsat": CpSatEngine}
```
Switching engines later = add `engine/<x>/` + a registry entry; domain/adapter
untouched.

### 3.5 Distilled scope vs. the production model

| Kept (Phase 1 core) | Deferred (future `enable_*` toggles) |
|---|---|
| Shift generation from rosters/availability + templates w/ breaks | Task flow (inbound OrderFlow chaining) |
| shift + task binaries, one-task-per-slot | Staging / floor / storage capacity, load management |
| Hourly coverage + unmet, all 3 families | Freezer warm-up breaks, productivity bands |
| One-shift-per-roster (soft) | Rotation rules, fair share, preferred OT/area, equipment caps |
| Weekly-hours + max-shifts/day + min-gap caps | Daily re-opt, fixed/published shifts |
| Lex objective: unmet → cost | Full OT1/OT2 day+week envelope (→ flat $/hr now) |
| Qualification gate | EBA grade-rate tables (→ single Base Rate now) |
| | The Phase-2A/B/C task-spec budget/hour-cap filtering |

### 3.6 Phase-1 done criteria
- `python run.py data/sample_tiny_input.json` solves in seconds and prints:
  per-function coverage %, total cost, unmet hours, solver status, and a schedule
  sample.
- `tests/test_engine_small.py`: a hand-built 2-member / 1-task instance with a
  known optimum (full coverage feasible → unmet 0; undersupplied → expected
  unmet). `tests/test_adapter.py`: adapter parses the fixture without loss.
- Result is deterministic (fixed CP-SAT seed).

---

## 4. Later phases (summary, for architectural continuity)

- **Backend (FastAPI):** sessions, scenarios CRUD, fixture select/upload,
  constraint preview/save, run trigger/status/results/schedule, insights,
  what-if/compare. SQLite (WAL). **Solve runs in a worker thread** (never blocks
  the event loop). Run marked `COMPLETED` on solve; **insights generated as a
  separate step** so an LLM failure can't fail a valid schedule.
- **LLM layer:** NL → solver-hook tools (`lock_worker_shift`,
  `set_min_workers_per_task`, `exclude_worker_from_task`, `scale_demand`,
  `set_max_hours`), **validated against scenario IDs**, applied as **soft**
  constraints (a bad tweak penalizes, never infeasible). Insight generator
  (metrics → structured report). Delta explainer (what-if). `LLMProvider`
  Protocol, Claude default.
- **Frontend:** Home → ScenarioEditor → RunHistory → ResultsView (coverage cards,
  demand-vs-served chart, insights, schedule table) → WhatIfView.
- **Deploy:** Docker Compose; Render free tier (persistent disk for SQLite,
  static frontend).

---

## 5. Open decisions (revisit before later phases)
- OT/cost fidelity: flat $/hr now; if cost realism matters, add an
  ordinary-vs-overtime split (real model splits normal/OT1/OT2, day & week).
- Coverage formulation: single per-hour `supply ≥ demand − unmet` (this doc) vs.
  the real two-layer (per-order volume balance **and** per-hour supply≥produced).
  Single-layer chosen for the distilled engine; revisit if order-level fidelity
  is needed.
- Fixture realism: 2-day / 12-member default — scale up once the engine is
  proven.
