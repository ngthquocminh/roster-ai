# ShiftMind — LLM Layer (v1.0, shipped)

## What This Is

ShiftMind (repo `rosterai`) is a workforce scheduling assistant: it loads a
distribution-centre week of workforce + demand data, runs a constraint solver
(OR-Tools CP-SAT) to produce a weekly schedule, and serves the result over an
HTTP API. Milestone v1.0 shipped the **LLM layer**: a user describes a
scheduling constraint change in plain English (any of five solver-hook tools),
it's validated and applied to the solve as a calibrated soft penalty, and a
separate on-demand endpoint turns run metrics into a grounded, plain-language
insight report. Two real, network-backed LLM providers (Gemini, OpenRouter)
sit behind a config-driven `LLMProvider` seam alongside the deterministic stub
that keeps default CI keyless.

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
- ✓ Insight generator: run metrics → structured, metric-grounded natural-language
  report; D-06 anti-fabrication guard rejects any uncited numeric token — Phase 3
- ✓ Insights generated as a **separate on-demand step** after the run, cached
  (`runs.insight_json`) — an LLM failure never invalidates a completed schedule
  (INS-01..04) — Phase 3
- ✓ Tests with a stubbed provider drive all default CI (no live LLM API); one
  gated `@pytest.mark.live` parity test per real provider confirms translation
  parity without running in CI — Phases 1–4
- ✓ Second real provider (OpenRouter, OpenAI-compatible SDK) added behind the
  same seam post-Phase-4, as a lower-friction alternative to Gemini's tight
  free-tier quota — quick tasks 260713-pn3/260713-stq

### Active

<!-- Next milestone candidates — surfaced during v1.0 but not yet scoped. -->

- [ ] Frontend / UI for constraint editing and insight viewing
- [ ] Fixture path traversal hardening in `constraint_service.py` (WR-04)
- [ ] `_grounding_guard` `coverage_by_day` dict-key admission fix (D-06 false-positive class)
- [ ] Demand scheduling: deadline-fill semantics instead of flat hourly distribution

### Out of Scope

<!-- Explicit boundaries, reviewed at v1.0 close. -->

- Frontend / React UI — deferred to a future milestone; v1.0 is API + engine only
- What-if compare + delta explanation — depends on the LLM layer having shipped (now true; still not scheduled)
- Deploy / AWS infra — out of scope until the feature set for a public-facing release is complete
- Hard/infeasible-making constraints from NL — all overrides apply as soft penalties only, by design (reaffirmed through v1.0)
- Production-model fidelity deferrals carried from design.md (OT1/OT2 cost split,
  two-layer coverage, task flow, capacity/load management) — not part of the LLM layer
- Extracting the solver engine into a separate service — noted as a clean future seam
  (`SchedulerEngine` Protocol) but not needed at current scale

## Context

- The backend (`backend/`) exposes the engine over FastAPI with a clean
  service/domain/engine layering; ~7,360 LOC Python as of v1.0 close.
- Two Protocol seams exist by design and both proved themselves under real
  swaps: `SchedulerEngine` (engine swap, unexercised beyond CP-SAT so far) and
  `LLMProvider` (vendor swap — stub → Gemini → OpenRouter, zero service/route
  changes required for either real-provider addition).
- The CP-SAT model is integer-only (time in minutes, volume/rate ×100). Soft
  constraints already exist in the model (e.g. `unfilled_roster`, `unmet_*`);
  the override mechanism extends that established penalty pattern, and all
  four override penalty constants are now empirically calibrated (ENG-04)
  rather than placeholder round numbers.
- `design.md` is the source-of-truth engineering design; `PLAN.md` is the
  hand-written phase tracker; `docs/decisions/` holds ADRs. This GSD project
  tracked Phases 1–4 (v1.0) in the GSD planning structure; see
  `.planning/milestones/v1.0-ROADMAP.md` for full phase detail.
- Known issues carried into the next milestone: a D-06 grounding-guard
  false-positive class on `coverage_by_day` dict-key citations (surfaced by
  live-provider testing, not yet fixed); no path-traversal containment check
  on the scenario fixture path in `constraint_service.py` (WR-04).

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
| Milestone scope = LLM layer only (4 phases) | Tight, shippable increment on top of the done engine+backend | ✓ Good — all 4 phases shipped, 100% v1 requirements complete |
| Include both NL constraint editing AND insight generation | Full "assistant" value needs both halves | ✓ Good — Phases 1–2 (constraints) and Phase 3 (insights) both shipped |
| Full engine wiring: apply overrides as soft constraints and re-solve | Delivers a real re-solved schedule, not just parsed intent | ✓ Good — verified never-infeasible across all 5 tools |
| First real LLM provider = Google Gemini (free tier), not Claude | No free Claude API tier; "use a free API first". Seam is provider-neutral, so Claude/others stay trivial future swaps | ✓ Good — `google-genai`, default `stub` keeps CI keyless |
| Stubbed provider for tests (no live API in CI) | Deterministic, cost-free CI | ✓ Good — 124 non-live tests, zero network calls in default CI |
| Add OpenRouter as a second real provider (post-Phase-4) | Gemini's 50-req/day free tier proved too tight for iterative live testing | ✓ Good — zero service/route changes needed, seam held |
| Provider-neutral translation boundary (`to_override_call`) | No vendor payload shape should leak past the LLM seam | ✓ Good — enabled 2 real-provider additions with zero seam changes |
| Defer penalty-weight calibration to Phase 4 | Needed real solver-run data to size constants correctly | ⚠️ Revisit — 3 phases of uncalibrated placeholders let a 100x `set_max_hours` scaling bug ship silently; calibrate earlier next time (see RETROSPECTIVE.md) |

## Current State

**Shipped:** v1.0 — LLM Layer (2026-07-15). All 4 phases complete, all v1
requirements validated, UAT (17/17) and security review (threats_open: 0)
both passed. See `.planning/MILESTONES.md` for the full entry and
`.planning/RETROSPECTIVE.md` for lessons learned.

## Next Milestone Goals

Candidates surfaced during v1.0 but not yet scoped into a milestone (see
`### Active` above for the full list):
- A frontend/UI so the NL constraint + insight flows are usable outside raw HTTP calls
- Closing the two known-issue carry-overs (D-06 `coverage_by_day` gap, fixture path traversal hardening)
- What-if compare + delta explanation, now that the LLM layer it depends on has shipped

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
*Last updated: 2026-07-15 — v1.0 (LLM Layer) milestone complete and archived*
