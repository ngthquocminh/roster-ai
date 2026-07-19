# ShiftMind — Frontend (v0.4, in progress)

## What This Is

ShiftMind (repo `rosterai`) is a workforce scheduling assistant: it loads a
distribution-centre week of workforce + demand data, runs a constraint solver
(OR-Tools CP-SAT) to produce a weekly schedule, and serves the result over an
HTTP API. Milestone v0.3 shipped the **LLM layer**: a user describes a
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
- ✓ RunHistory — trigger a run, poll status (self-terminating), list prior
  runs with created/started/finished timing, honest in-flight copy with no
  cancel/progress affordance, inline FAILED error text — Validated in Phase 3:
  run-execution-history

### Active

<!-- v0.4 scope — building toward these. -->

- [ ] Vite + React + TypeScript app under `frontend/`, typed against `docs/API.md`
- [ ] Home — scenario list / create from an existing fixture
- [x] ScenarioEditor — fixture select, NL constraint box, applied-overrides list — ✓ v0.4 Phase 2 (scenario detail header + 404 gate, plain-English constraint transcript with distinct outcome treatments, durable applied-overrides list over GET /scenarios/{id}/overrides)
- [ ] ResultsView — coverage cards, demand-vs-served chart, insights, schedule table
- [ ] CORS middleware on the FastAPI app (enabler — no browser origin can call the API without it)

<!-- Deferred: scoped out of v0.4, still live. See todos/pending/ for the full set. -->

- [ ] Input upload endpoint — deferred to v0.5; vision.md's pitch opens with it, but v0.4 demos against committed fixtures. Hard prerequisite WR-04 is now resolved (see below).
- [x] Fixture path traversal hardening (WR-04) — ✓ resolved in Phase 2 code-review fix: `settings.resolve_fixture_path()` constrains the fixture path to `data_dir`, rejecting absolute / `../`-escaping values (400 on scenario create, 404 on constraint parse)
- [ ] `_grounding_guard` `coverage_by_day` dict-key admission fix (D-06 false-positive class)
- [ ] Demand scheduling: deadline-fill semantics instead of flat hourly distribution

### Out of Scope

<!-- Explicit boundaries, reviewed at v0.3 close. -->

- What-if compare + delta explanation — unblocked (the LLM layer it depends on shipped),
  but deliberately held out of v0.4: it's a second large feature on top of a from-scratch
  React app, and two big things in one milestone is how scope slips. Revisit for v0.5.
- Auth / sessions — never built; vision.md's localStorage session UUID never happened.
  Out of scope until a deploy makes it necessary (see v0.4 key context #1).
- Deploy / AWS infra — out of scope until the feature set for a public-facing release is complete
- Hard/infeasible-making constraints from NL — all overrides apply as soft penalties only, by design (reaffirmed through v0.3)
- Production-model fidelity deferrals carried from design.md (OT1/OT2 cost split,
  two-layer coverage, task flow, capacity/load management) — not part of the LLM layer
- Extracting the solver engine into a separate service — noted as a clean future seam
  (`SchedulerEngine` Protocol) but not needed at current scale

## Context

- The backend (`backend/`) exposes the engine over FastAPI with a clean
  service/domain/engine layering; ~7,360 LOC Python as of v0.3 close.
- Two Protocol seams exist by design and both proved themselves under real
  swaps: `SchedulerEngine` (engine swap, unexercised beyond CP-SAT so far) and
  `LLMProvider` (vendor swap — stub → Gemini → OpenRouter, zero service/route
  changes required for either real-provider addition).
- The CP-SAT model is integer-only (time in minutes, volume/rate ×100). Soft
  constraints already exist in the model (e.g. `unfilled_roster`, `unmet_*`);
  the override mechanism extends that established penalty pattern, and all
  four override penalty constants are now empirically calibrated (ENG-04)
  rather than placeholder round numbers.
- `docs/design.md` is the source-of-truth engineering design (the durable
  "why"); `.planning/` (`STATE.md`/`ROADMAP.md`/`MILESTONES.md`) owns the
  planning lifecycle — the hand-written phase tracker it replaced was retired
  at the v0.3/v0.4 boundary. No ADR directory exists in this repo; decisions
  live in this file's own Key Decisions table, `.planning/RETROSPECTIVE.md`,
  and `docs/design.md` §6 (open decisions). `docs/vision.md` is the origin
  snapshot this document descends from. This GSD project tracked Phases 1–4
  (v0.3) in the GSD planning structure; see `.planning/milestones/v0.3-ROADMAP.md`
  for full phase detail.
- Known issues carried into the next milestone: a D-06 grounding-guard
  false-positive class on `coverage_by_day` dict-key citations (surfaced by
  live-provider testing, not yet fixed). WR-04 (no path-traversal containment
  on the scenario fixture path) was resolved in Phase 2's code-review fix pass.

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

## Current Milestone: v0.4 Frontend (React UI)

**Goal:** Make the shipped engine + LLM layer usable in a browser — create a
scenario from a fixture, express a constraint in plain English, run a solve, and
read the schedule + insights without touching curl.

**Target features:**
- Vite + React + TypeScript app under `frontend/`
- Home → scenario list / create
- ScenarioEditor → fixture select, NL constraint box, applied-overrides list
- RunHistory → trigger run, poll status, list runs
- ResultsView → coverage cards, demand-vs-served chart, insights, schedule table
- Typed API client written against `docs/API.md`
- CORS middleware on FastAPI — the one backend change, a mandatory enabler

**Explicitly deferred from v0.4:** input upload (v0.5), what-if compare + delta
explanation, D-06 grounding-guard fix, WR-04 traversal hardening.

### v0.4 key context — noted for later handling

Surfaced during v0.4 scoping (2026-07-15). None block the milestone; recorded
here so they are not rediscovered mid-build or lost between sessions.

| # | Context | Bearing on v0.4 |
|---|---------|-----------------|
| 1 | **No auth exists.** vision.md assumed a localStorage session UUID; it was never built. Every scenario is globally visible to any caller. | v0.4 ships without auth. Any public/shared deploy needs this resolved first — a real gate on the AWS deploy already in Out of Scope. **Handle later.** |
| 2 | **Insights use a two-shape contract behind one status code.** `GET /runs/{id}/insights` returns `200` with `ready:false` when the run isn't `COMPLETED` — deliberately *not* 409 — and `502` on generation failure. `/runs/{id}/result` by contrast *does* 409 before completion. | **v0.4 implementation fact, not deferrable.** The client must branch on `ready`, not on status code, and must not treat the two endpoints alike. Documented in `docs/API.md`. |
| 3 | **Solves are slow and uncancellable.** Round-2 cost-optimality is a ~2min tail vs ~20s for round 1, on a single-worker `ThreadPoolExecutor` with no cancel path. | v0.4 needs honest loading/progress states for a wait it can neither shorten nor abort. Cancellation + concurrency limits and the round-2 relative-gap stop are both in `todos/pending/`. **Handle later.** |
| 4 | **`LLM_PROVIDER` defaults to `stub`** — keyless, deterministic, regex-routed. Real NL parsing needs `gemini` or `openrouter` configured. | Config, not code. A demo showing genuine NL understanding must set a real provider; default CI stays keyless and must remain so. |
| 5 | **No CORS on the FastAPI app.** | Promoted from context to a v0.4 requirement — a browser origin cannot call the API without it. |

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
*Last updated: 2026-07-19 — Phase 3 (run-execution-history) complete*
