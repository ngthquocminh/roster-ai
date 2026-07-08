# ShiftMind — LLM Layer (Phase 3)

## What This Is

ShiftMind (repo `rosterai`) is a workforce scheduling assistant: it loads a
distribution-centre week of workforce + demand data, runs a constraint solver
(OR-Tools CP-SAT) to produce a weekly schedule, and serves the result over an
HTTP API. This GSD milestone adds the **LLM layer**: describe constraint tweaks
in plain English and have them applied to the solve, and turn run metrics into a
plain-language insight report.

## Core Value

A user can express a scheduling constraint change in plain English and get back a
re-solved schedule that honors it (as a soft constraint) plus a readable
explanation of what changed — without touching solver code or JSON.

## Requirements

### Validated

<!-- Shipped and confirmed valuable — Phases 1–2, already built and committed. -->

- ✓ Distilled CP-SAT scheduling engine (shift gen, shift↔task link, hourly
  coverage + unmet, qualification gate, hours/shift/gap caps) — Phase 1
- ✓ Lexicographic objective (unmet → cost) via solve-and-lock with graceful
  round-2 timeout degradation — Phase 1
- ✓ Pure domain model + input adapter (real-schema JSON → `SchedulingProblem`,
  all 3 demand families) — Phase 1
- ✓ `SchedulerEngine` Protocol + factory (pluggable solver seam) — Phase 1
- ✓ Fixture tool + committed tiny full-week fixture — Phase 1
- ✓ FastAPI backend: scenario CRUD, run trigger/status/results over HTTP — Phase 2
- ✓ Solve runs in a worker thread (never blocks the event loop) — Phase 2
- ✓ SQLite (WAL) persistence; `overrides` JSON column reserved on scenarios — Phase 2
- ✓ `LLMProvider` Protocol + stub provider seam (partial-apply parse contract) — Phase 1
- ✓ NL constraint parser: plain English → all five validated solver-hook tool calls
  (`lock_worker_shift`, `set_min_workers_per_task`, `exclude_worker_from_task`,
  `scale_demand`, `set_max_hours`), with a readable `parsed_constraint` echo — Phase 2
- ✓ Tool-call validation against real scenario IDs + arg bounds (reject unknown
  member/task refs and out-of-range values with plain-English guidance) — Phase 2
- ✓ Apply overrides as **soft** constraints in the CP-SAT solve and re-solve — all
  five tools penalize, never make the model infeasible (verified) — Phases 1–2
- ✓ Degenerate-re-solve detection: `SolveResult.warnings` flags families with real
  demand but zero served hours, without touching solver status (ENG-05) — Phase 2
- ✓ Real network-backed LLM provider behind the `LLMProvider` Protocol —
  **Google Gemini (free tier) via `google-genai`**, config-driven provider + model id
  (default `stub` keeps CI keyless); native function-calling → shared `to_override_call`
  parity path with the stub; one `@pytest.mark.live` parity test excluded from default CI
  (LLM-02, TEST-04) — Phase 4
- ✓ Penalty weights empirically calibrated against the committed full-week fixture
  (sweep harness + real-engine regressions: satisfiable honored, unsatisfiable degrades
  without dominating round-2 cost; folded ENG-05 real-engine degeneracy test) (ENG-04) — Phase 4

### Active

<!-- This milestone — Phase 3 LLM layer. Hypotheses until shipped and validated. -->

- [ ] Insight generator: run metrics → structured natural-language report
- [ ] Insights generated as a **separate step** after the run (an LLM failure
      can't fail a valid schedule)
- [ ] Tests with a stubbed provider (no live LLM API in CI)

### Out of Scope

<!-- Explicit boundaries for this milestone. -->

- Frontend / React UI (Phase 4) — this milestone is API + engine only
- What-if compare + delta explanation (Phase 5) — depends on the LLM layer landing first
- Deploy / AWS infra (Phase 5) — out of scope until the feature set is complete
- Live LLM calls in CI — tests use a stubbed provider
- Hard/infeasible-making constraints from NL — all overrides apply as soft penalties
- Production-model fidelity deferrals carried from design.md (OT1/OT2 cost split,
  two-layer coverage, task flow, capacity/load management) — not part of the LLM layer

## Context

- The backend (`backend/`) already exposes the engine over FastAPI with a clean
  service/domain/engine layering; the `overrides` JSON column on scenarios was
  reserved in Phase 2 specifically for these NL constraints.
- Two Protocol seams exist by design: `SchedulerEngine` (engine swap) and the
  planned `LLMProvider` (vendor swap). Claude is the default LLM provider; Gemini
  is a later possibility behind the same seam.
- The CP-SAT model is integer-only (time in minutes, volume/rate ×100). Soft
  constraints already exist in the model (e.g. `unfilled_roster`, `unmet_*`), so
  the override mechanism extends an established penalty pattern.
- `design.md` is the source-of-truth engineering design; `PLAN.md` is the
  hand-written phase tracker; `docs/decisions/` holds ADRs. This GSD project
  formalizes Phase 3 into the GSD planning structure.

## Constraints

- **Tech stack**: Python backend, OR-Tools CP-SAT solver, FastAPI, SQLite (WAL),
  uv-managed deps — established in Phases 1–2, not up for change in this milestone.
- **Architecture**: Domain stays pure (no solver/web/LLM imports); LLM access goes
  behind an `LLMProvider` Protocol; overrides applied only in the engine layer.
- **Safety**: NL-derived constraints must be validated against real scenario IDs
  and applied as soft constraints only — never able to make a solve infeasible.
- **Resilience**: Insight generation is a separate post-run step so an LLM failure
  never invalidates a successfully computed schedule.
- **Testing**: No live LLM API in CI — a stubbed provider must drive tests.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Milestone scope = Phase 3 only (LLM layer) | Tight, shippable increment on top of the done engine+backend | — Pending |
| Include both NL constraint editing AND insight generation | Full Phase 3 as designed; the two halves of the "assistant" value | — Pending |
| Full engine wiring: apply overrides as soft constraints and re-solve | Delivers a real re-solved schedule, not just parsed intent | — Pending |
| First real LLM provider = Google Gemini (free tier), not Claude | No free Claude API tier; "use a free API first". Seam is provider-neutral, so Claude/others stay trivial future swaps | ✓ Phase 4 — `google-genai`, default `stub` keeps CI keyless |
| Stubbed provider for tests (no live API in CI) | Deterministic, cost-free CI | — Pending |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-07-08 — Phase 4 (Real LLM Provider + Penalty Calibration) complete; final phase of the milestone*
