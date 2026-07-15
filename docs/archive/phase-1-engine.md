# Phase 1 — Scheduling Engine + data spine

> **Archived historical plan doc — not maintained.** Kept as a record of how
> this phase was built. Its durable design now lives in [`../design.md`](../design.md)
> §3; project status lives in `.planning/`.
>
> **Status: ✅ Completed** (engine `06799e9`; fixture + lex hardening `44436bd`).
> Written retroactively to match the per-phase doc workflow the project used at
> the time; it records the plan and design as built.

## Goal

Build the core that turns a real-schema weekly input into a weekly schedule with
coverage and cost metrics: a small **fixture** of real-shaped data → an
**adapter** to a pure-domain problem → a **CP-SAT engine** → a **CLI** that
prints the result. A distilled reimplementation of a production weekly scheduler.
No web, no LLM, no persistence.

## Targets (acceptance criteria)

- [x] `run.py <input> cpsat [time_limit_s]` loads a real-schema fixture, solves,
      and prints per-function & per-day coverage %, total cost, unmet hours,
      solver status, and a schedule sample.
- [x] All **three demand families** (outbound volume, inbound volume, indirect
      headcount) are ingested and covered.
- [x] Objective is **lexicographic**: minimize unmet labour-hours first, then cost.
- [x] A **time-limited** solve returns the unmet-optimal schedule (cost not yet
      minimized) instead of failing.
- [x] Deterministic result (fixed CP-SAT seed).
- [x] The solver is behind a **seam** so a different backend can be swapped in
      without touching the domain or adapter.
- [x] Tests green: `test_engine_small` (known optimum) + `test_adapter` (fixture
      parses without loss).

## Design

**Layering** (dependencies point inward): `engine → domain ← ingest`, with
`fixtures` and `config` as supporting infra. The domain is pure Python (no
solver/web imports).

```
backend/
  fixtures/build_short_input.py   # full weekly JSON -> small coherent fixture
  ingest/
    input_adapter.py              # real-schema JSON -> SchedulingProblem
    scenario_time.py              # datetime <-> hours-from-start helpers
  domain/
    types.py                      # Member, Task, Demand*, ShiftTemplate, ...
    problem.py                    # SchedulingProblem (engine input)
    result.py                     # SolveResult, ScheduleRow, SummaryMetrics
  engine/
    base.py                       # SchedulerEngine Protocol, SolverConfig, factory
    cpsat/
      builder.py                  # SchedulingProblem -> CP-SAT vars + constraints
      objective.py                # lexicographic solve-and-lock rounds
      engine.py                   # CpSatEngine implements SchedulerEngine
  config/constants.py             # caps, rates, scaling knobs
  run.py                          # load fixture -> solve -> print metrics
```

**Time & units.** Time is **hours from the scenario start** (day-2 06:00 =
`30.0`); the model works in integers (CP-SAT is integer-only) with volume/rate
scaled ×100. Coverage is bucketed per integer hour.

**Decision variables.** `shift[m, window, template, start]` (candidate shift),
`task[m, shift, task_id, slot]` (member does a task in a shift slot;
shifts >6h get 2 slots), `unmet_*[task, hour]` (shortfall), `unfilled_roster`
(soft non-fill).

**Constraints.** Shift↔task link (task ≤ shift, ≥1 task per selected shift, one
task per slot); soft roster fill; per-task-hour coverage (OB/IB:
`Σ rate·overlap·absenteeism + unmet ≥ demand`; IND: `Σ headcount + unmet ≥
required`); qualification gate (task vars only for qualified pairs); weekly-hours
/ max-shifts-per-day / min-gap caps.

**Objective — lexicographic via solve-and-lock** (CP-SAT has no native lex):
round 1 minimizes unmet labour-hours and records the optimum; round 2 adds
`unmet ≤ r1` and minimizes cost. Round 2 re-solves and would overwrite round 1's
solution, so the round-1 solution is **snapshotted** — a round-2 timeout falls
back to it (status `UNKNOWN`, unmet-optimal) instead of crashing.

**Fixture tool** — shrinks a full weekly input **vertically** (keep the whole
week; cut tasks/members) so coverage reports span all 7 days. It keeps only tasks
with coherent supply (≥1 qualified, rostered member), pulls in those members, and
scales demand to the kept workforce's **actual roster-window hours** so coverage
lands in an informative band. Output: ~410 KB, 11 members, 6 tasks across 3
families, full 7-day week.

**Engine seam** — `SchedulerEngine` Protocol + `create_engine(name)` registry
(`{"cpsat": CpSatEngine}`). Swapping a backend = add `engine/<x>/` + a registry
entry; domain/adapter untouched.

See [`design.md`](../design.md) §3.4 for the full model and §3.5 for the
distilled-scope (kept vs deferred) table.

## Step-by-step plan

1. Fixture tool (`fixtures/build_short_input.py`) — coherent vertical shrink.
2. Domain types (`domain/`) — `Member`, `Task`, `ShiftTemplate`, `DemandBand`,
   `SchedulingProblem`, `SolveResult` + metrics.
3. Adapter (`ingest/`) — real-schema JSON → `SchedulingProblem`; time helpers.
4. CP-SAT builder (`engine/cpsat/builder.py`) — vars + constraints + coverage.
5. Lexicographic objective (`engine/cpsat/objective.py`) — solve-and-lock + snapshot.
6. Engine + seam (`engine/cpsat/engine.py`, `engine/base.py`).
7. CLI (`run.py`).
8. Tests — `test_engine_small.py`, `test_adapter.py`.
9. uv-managed deps (`pyproject.toml` + `uv.lock`).

## Decisions / open questions (resolved)

- **Real-schema JSON input via an adapter, not demo CSVs**, and **consume the
  materialized Workload tables** rather than regenerating demand from Order
  Volume (site-flow/conversions out of scope). Validates the model on real data
  shapes from day one. (See [`design.md`](../design.md) §3.2, §3.7.)
- **Lexicographic objective, not a weighted sum** — coverage must never be traded
  for cost; lex makes that a hard guarantee, not a weight-tuning artifact.
- **Shift templates from input data, not hardcoded** — templates + breaks vary by
  site/agreement.
- **Vertical fixture shrink (full week), demand scaled to real capacity** — so the
  coverage report is informative across all 7 days rather than ~2% or 100%.
- **Single-layer coverage** (`supply ≥ demand − unmet`) for the distilled engine;
  the production two-layer (order-volume balance + supply≥produced) is an open
  decision in [`design.md`](../design.md) §5.

## Outcome

Shipped all targets. Solves the 11-member / 6-task / 3-family full-week fixture:
unmet-optimal in ~20s; proving cost-optimality is the slow tail (~2 min), and a
short time limit degrades gracefully to the unmet-optimal schedule. Deterministic
under a fixed seed. 5 tests pass (2 engine + 3 adapter).

**Notes / open items carried forward:** proving cost-optimality is slow on the
full week — consider a round-2 relative-gap stop (raised again when the API/UI
drive runs interactively); fixture realism (member/task counts) can scale up once
the engine is proven. (See [`design.md`](../design.md) §5.)
