# ShiftMind

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
that keeps default CI keyless. Milestone v0.4 shipped the **frontend**: the
full assistant is now usable end-to-end from a browser — create a scenario
from a fixture, shape it with plain-English constraints, trigger a solve and
watch it run, and read the resulting schedule, coverage, and insight report —
without ever touching curl or raw JSON.

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
- ✓ ResultsView — coverage summary cards + warnings banner + by-day table,
  demand-vs-served chart (with honest empty-state for zero-demand runs,
  closed via gap-closure G-04-4), scrollable schedule table, on-demand
  insight report with five-state branching on the response's `ready` field
  (never the status code) — Validated in Phase 4: results-insights
- ✓ Vite + React + TypeScript app under `frontend/`, typed against `docs/API.md`
  (openapi-typescript/openapi-fetch codegen, zero hand-authored payload shapes) — v0.4 Phase 1
- ✓ CORS middleware on the FastAPI app, env-driven allow-list, no wildcard/credentials — v0.4 Phase 1 (BE-01)
- ✓ Home — scenario list (all 5 UI states) / create from a backend-offered fixture, no upload path — v0.4 Phase 1
- ✓ Persistent 4-route nav shell with deep-linkable routes and honest
  not-built-yet placeholders (fully retired as each real view landed) — v0.4 Phase 1
- ✓ Fixture path traversal hardening (WR-04) — resolved in Phase 2 code-review fix:
  `settings.resolve_fixture_path()` constrains the fixture path to `data_dir`,
  rejecting absolute / `../`-escaping values (400 on scenario create, 404 on constraint parse)

### Active

<!-- Carried forward from v0.4, still unaddressed. Candidates for v0.5 scoping. -->

- [ ] Input upload endpoint — vision.md's pitch opens with it, but v0.3/v0.4 demoed against committed fixtures. Hard prerequisite WR-04 is now resolved, so this is unblocked (v2 UP-01).
- [ ] `_grounding_guard` `coverage_by_day` dict-key admission fix (D-06 false-positive class) — live path to a 502 from `GET /runs/{id}/insights`; v0.4's ResultsView survives it (RES-05) but the root cause is unfixed (v2 D-06-FIX)
- [ ] Demand scheduling: deadline-fill semantics instead of flat hourly distribution
- [ ] What-if compare + delta explanation — unblocked (LLM layer + frontend both shipped), deliberately held out of v0.3 and v0.4 as a second large feature
- [ ] Run cancellation + concurrency limits (v2 OPS-01) and round-2 relative-gap stop (v2 OPS-02) — single-worker pool, no cancel path; v0.4 ships an honest uncancellable wait instead

### Out of Scope

<!-- Explicit boundaries, reviewed at v0.3 close. -->

- What-if compare + delta explanation — unblocked (the LLM layer it depends on shipped),
  but deliberately held out of v0.4: it's a second large feature on top of a from-scratch
  React app, and two big things in one milestone is how scope slips. Revisit for v0.5.
- Auth / sessions — never built; vision.md's localStorage session UUID never happened.
  Out of scope until a deploy makes it necessary (see Context).
- Deploy / AWS infra — out of scope until the feature set for a public-facing release is complete
- Hard/infeasible-making constraints from NL — all overrides apply as soft penalties only, by design (reaffirmed through v0.3)
- Production-model fidelity deferrals carried from design.md (OT1/OT2 cost split,
  two-layer coverage, task flow, capacity/load management) — not part of the LLM layer
- Extracting the solver engine into a separate service — noted as a clean future seam
  (`SchedulerEngine` Protocol) but not needed at current scale

## Context

- The backend (`backend/`) exposes the engine over FastAPI with a clean
  service/domain/engine layering; ~7,360 LOC Python as of v0.3 close. The
  frontend (`frontend/`) adds ~10,287 LOC TypeScript as of v0.4 close: Vite +
  React 19 + TanStack Query + shadcn/ui (Tailwind v4) + recharts.
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
  planning lifecycle. No ADR directory exists in this repo; decisions live in
  this file's own Key Decisions table, `.planning/RETROSPECTIVE.md`, and
  `docs/design.md` §6 (open decisions). `docs/vision.md` is the origin
  snapshot this document descends from. Full phase detail for both shipped
  milestones lives in `.planning/milestones/v0.3-ROADMAP.md` and
  `.planning/milestones/v0.4-ROADMAP.md`.
- `GET /runs/{id}/insights` returns `200` with `ready:false` when the run
  isn't `COMPLETED` (deliberately not `409`) and `502` on generation failure —
  `GET /runs/{id}/result` by contrast does `409` before completion. Any client
  against this API must branch on `ready`, never on status code, and must not
  treat the two endpoints alike. Documented in `docs/API.md`; the frontend's
  `InsightPanel` (v0.4 Phase 4) is the reference implementation of this rule.
- `LLM_PROVIDER` defaults to `stub` (keyless, deterministic, regex-routed).
  Real NL parsing needs `gemini` or `openrouter` configured — config, not
  code. Default CI stays keyless and must remain so.
- No auth exists anywhere in the stack; every scenario is globally visible to
  any caller. Out of scope until a public/shared deploy makes it necessary
  (see Out of Scope).
- Known issue carried forward: a D-06 grounding-guard false-positive class on
  `coverage_by_day` dict-key citations (surfaced by live-provider testing,
  not yet fixed) — still a live path to a `502` from `GET /runs/{id}/insights`,
  which the frontend's RES-05 isolation now survives without being fixed at
  the source. WR-04 (fixture path traversal) was resolved in v0.4 Phase 2's
  code-review fix pass — no longer an open issue.

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
| Roadmap = 4 phases, numbered 1-4; phase numbering restarts every milestone | Each milestone owns its own 1..N sequence, unambiguous within its own ROADMAP.md; shipped milestones keep numbering in their archives | ✓ Good — no on-disk collisions, adopted as the standing convention |
| BE-01 (CORS) bundled into Phase 1 rather than its own phase | Hard gate but a small change; keeps Phase 1 an observable slice instead of a one-line phase | ✓ Good |
| SCEN-03 grouped with CONS-* in Phase 2, not with SCEN-01/02 in Phase 1 | The overrides-list view IS the surface constraint submission populates; splitting would strand a half-built view across two phases | ✓ Good |
| SHELL-03 (four-view nav) assigned to Phase 1 as the routing/nav capability | Later phases mount their view into the shell established here; Phase 1's criterion scoped to what's verifiable then | ✓ Good |
| No dedicated research phase for v0.4 | React SPA over a documented REST API judged well-trodden; open choices (charting library, polling strategy, client typing) deliberately left to plan-phase | ✓ Good — zero rework traced to this omission |

<details>
<summary>Archived: v0.4 Frontend (React UI) milestone scope — SHIPPED 2026-07-20</summary>

**Goal:** Make the shipped engine + LLM layer usable in a browser — create a
scenario from a fixture, express a constraint in plain English, run a solve, and
read the schedule + insights without touching curl.

**Target features (all shipped):**
- Vite + React + TypeScript app under `frontend/`
- Home → scenario list / create
- ScenarioEditor → fixture select, NL constraint box, applied-overrides list
- RunHistory → trigger run, poll status, list runs
- ResultsView → coverage cards, demand-vs-served chart, insights, schedule table
- Typed API client written against `docs/API.md`
- CORS middleware on FastAPI — the one backend change, a mandatory enabler

**Deferred from v0.4** (see Requirements → Active): input upload, what-if
compare + delta explanation, D-06 grounding-guard fix, run cancellation.

Full phase detail: `.planning/milestones/v0.4-ROADMAP.md`. Full requirements
traceability: `.planning/milestones/v0.4-REQUIREMENTS.md`. Milestone audit:
`.planning/milestones/v0.4-MILESTONE-AUDIT.md`.

</details>

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
*Last updated: 2026-07-20 — after v0.4 milestone completion (full evolution review)*
