---
gsd_state_version: 1.0
milestone: v0.4
milestone_name: Frontend
current_phase: 4
current_phase_name: Results & Insights
status: executing
stopped_at: Phase 04 UI-SPEC approved
last_updated: "2026-07-19T20:18:38.114Z"
last_activity: 2026-07-19
last_activity_desc: Phase 03 complete, transitioned to Phase 4
progress:
  total_phases: 4
  completed_phases: 3
  total_plans: 20
  completed_plans: 20
  percent: 75
---

# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-07-15)

**Core value:** A user can express a scheduling constraint change in plain English and get back a re-solved schedule that honors it (as a soft constraint) plus a readable explanation of what changed.
**Current focus:** Phase 03 — run-execution-history

## Current Position

Phase: 4 — Results & Insights
Plan: Not started
Status: Ready to execute
Last activity: 2026-07-19 — Phase 03 complete, transitioned to Phase 4

## Performance Metrics

**Velocity:**

- Total plans completed: 23
- Average duration: — min
- Total execution time: 0 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01 | 7 | - | - |
| 02 | 7 | - | - |
| 03 | 6 | - | - |
| 04 | 3 | - | - |

**Recent Trend:**

- Last 5 plans: —
- Trend: —

*Updated after each plan completion*
| Phase 01 P01 | 7 | 2 tasks | 6 files |
| Phase 01 P03 | 8 | 2 tasks | 2 files |
| Phase 02 P01 | 6 | 3 tasks | 5 files |
| Phase 02 P03 | 15 | 2 tasks | 4 files |
| Phase 02 P02 | 13 | 3 tasks | 6 files |
| Phase 02 P04 | 2 | 2 tasks | 1 files |
| Phase 03 P01 | 4 | 3 tasks | 8 files |
| Phase 03 P02 | 17 | 2 tasks | 2 files |
| Phase 04 P01 | 8min | 3 tasks | 6 files |
| Phase 04 P03 | 45min | 3 tasks | 3 files |
| Phase 04 P02 | 60min | 3 tasks | 5 files |
**Per-Plan Metrics:**

| Plan | Duration | Tasks | Files |
|------|----------|-------|-------|
| Phase 02 P01 | 20min | 2 tasks | 5 files |
| Phase 02 P02 | 20min | 2 tasks | 5 files |
| Phase 02 P03 | 15min | 2 tasks | 6 files |
| Phase 02 P04 | 25min | 2 tasks | 5 files |
| Phase 02 P05 | 35min | 2 tasks | 7 files |
| Phase 02 P06 | 15min | 2 tasks | 4 files |

## Accumulated Context

### Decisions

v0.3 decisions are logged in full in PROJECT.md's Key Decisions table and
`.planning/RETROSPECTIVE.md`. Cleared here at milestone close — start fresh
for the next milestone's decisions.

v0.4 decisions:

- **Roadmap = 4 phases, numbered 1-4 — phase numbering RESTARTS at each milestone.** Chosen 2026-07-15 (reversing the roadmapper's initial continue-from-4 default, which would have made v0.4 Phases 5-8). Each milestone now owns its own 1..N sequence; shipped milestones keep their numbering in their archived roadmaps. Safe because `.planning/phases/` was empty — v0.3's phase directories were archived to `milestones/v0.3-phases/` at milestone close, so `/gsd-plan-phase 1` cannot collide on disk. ROADMAP.md's Progress table is scoped to the current milestone only, so "Phase 1" is unambiguous within it.
- **BE-01 (CORS) placed in Phase 1, not a phase of its own.** It is a hard gate (no browser origin can call the API without it) but a small change; bundling it with the scaffold makes Phase 1 an observable slice instead of a one-line phase.
- **SCEN-03 grouped with CONS, not with SCEN-01/02.** "See the overrides currently applied" *is* the ScenarioEditor surface that constraint submission populates — splitting them would strand a half-built view across two phases.
- **SHELL-03 (four-view nav) assigned to Phase 1** as the routing/nav capability; later phases mount their views into the shell. Phase 1's criterion is scoped to what is verifiable then (nav + deep-linkable routes, later views as reachable placeholders).
- **No research phase for v0.4.** A React SPA over a documented REST API was judged well-trodden; the open choices (charting library, polling strategy, client typing approach) are deliberately left to plan-phase where they are concrete.
- [Phase ?]: Dedicated GET /scenarios/{id}/overrides endpoint (not a ScenarioOut field) so scenario-detail and overrides fetches resolve/error independently per UI-SPEC
- [Phase ?]: constraints.test.ts mirrors scenarios.test.ts's vi.mock("./client") boundary-mock pattern verbatim (not msw) for the applyConstraint wrapper
- [Phase ?]: Textarea added via npx shadcn add textarea from the official registry (source-file copy), verified zero new package.json dependencies
- [Phase ?]: useApplyConstraint's docstring avoids literal 'textarea-clear'/'transcript-append' substrings so the plan's own no-textarea/transcript-logic acceptance grep can't false-positive on an explanatory comment.
- [Phase ?]: ScenarioHeader/OverridesList take the useQuery result object as props (scenarioQuery/overridesQuery) rather than a scenarioId, so plan 02-06's Editor can share one useScenario instance between the header and useOverrides's enabled gate
- [Phase ?]: 404 'Back to Scenarios' uses a plain Link with buttonVariants() classes instead of Button asChild + Radix Slot, avoiding an untested Slot+react-router-Link ref-forwarding combo with no repo precedent
- [Phase ?]: ProviderDownBanner carries a stable data-testid="provider-down-banner" so tests can positively assert it is NOT a destructive-variant element (no analog component had this need)
- [Phase ?]: 503 provider-down is structurally disjoint from the 200-body rejection render path — ProviderDownBanner renders directly in ConstraintInput from applyConstraint.error.status, never flows through onOutcome/the transcript
- [Phase ?]: Task 1 (Editor composition, App.tsx rewire, EditorPlaceholder retirement) was already committed from a prior session; this run verified it against plan requirements and completed/committed Task 2 (Editor.test.tsx + router.test.tsx update)

### Pending Todos

[From .planning/todos/pending/ — ideas captured during sessions]

- [WR-04 / api]: Harden scenario fixture path against traversal — add containment check before `json.load` in `constraint_service.py:152`
- [testing]: Add real-engine test for ENG-05 degeneracy detection (WR-05) — current tests validate a copied mirror, not `CpSatEngine.solve()` — ⚠️ no file in `todos/pending/`; STATE-only entry, needs capture or removal
- [engine / improvement]: Demand scheduling should target deadline fill, not flat hourly distribution — `_aggregate_demand` spreads volume demand evenly per hour but real requirement is to accumulate labour before `b.end_h`; INDIRECT (headcount) demand is fine as-is (`builder.py:111`)
- [architecture / post-POC]: Extract solver engine into a separate service + master run-manager — FastAPI becomes thin API+LLM layer; `SchedulerEngine` Protocol is already the clean seam for this split

Migrated out of `docs/PLAN.md` at the v0.3/v0.4 boundary, when that hand-written
tracker was retired in favour of `.planning/`. These were its Phase 1/2
"⏸ deferred/optional" follow-ups and existed nowhere in GSD:

- [engine / tuning]: Tune DEMAND_LOAD and task mix for even coverage band — Receiving ~10%, Pick ~35% on the committed fixture; cosmetic/demo-quality only (`build_short_input.py:49`)
- [engine / performance]: Add round-2 relative-gap stop to bound solve time — cost-optimality proof is a ~2min tail vs ~20s round 1; matters now runs are interactive; rationale in `design.md` §6 (`objective.py:47`) — **bears on v0.4 Phase 3 (RUN-03)**: the wait this todo would shorten is the wait Phase 3 must communicate honestly
- [api / concurrency]: Add run cancellation and concurrency limits — single-worker pool, no way to stop an in-flight solve; overlaps the engine-as-a-service todo (`run_service.py:38`) — **bears on v0.4 Phase 3 (RUN-03)**: v0.4 ships an honest "cannot be cancelled" wait rather than a cancel path (v2 OPS-01)
- [api / ingest]: Add input upload endpoint — scenarios only creatable from fixtures already in `data/`; `vision.md`'s pitch opens with "Upload workforce & demand data", so this is intent-vs-built drift. Deferred to v0.5 (v2 UP-01); must land after WR-04 traversal hardening (`fixtures.py:14`)
- [api / engine]: Add per-scenario engine selection — always `cpsat`; `SchedulerEngine` seam unproven by a second real solver (`base.py:33`)

### Blockers/Concerns

[Issues that affect future work — carried forward from v0.3]

- [llm / insight_service]: `_grounding_guard`/`_allowed_values` in `services/insight_service.py` never admits `coverage_by_day` dict KEYS (day-index labels like "Day 0"), only their percentage VALUES — a model that writes "Day 0: 61.22%" gets the bare `0` rejected as ungrounded (D-06 false positive). Surfaced 2026-07-13 by the live OpenRouter `generate_insights` test once the upstream-429 blocker on the old default model was fixed (quick task 260713-stq); was invisible before because no live run had reached the guard with a real completion. Needs a follow-up decision: widen `_allowed_values()` to admit day-index integers, or adjust the insight prompt to avoid citing bare day-index numbers. **Bears on v0.4 Phase 4 (RES-05):** this is a live path to a `502` from `GET /runs/{id}/insights` — it is exactly the failure RES-05's "results view stays intact" criterion must survive. The fix itself stays out of v0.4 (v2 D-06-FIX); the UI must simply not fall over when it fires.

### Quick Tasks Completed

| # | Description | Date | Commit | Directory |
|---|-------------|------|--------|-----------|
| 260708-e7z | Add .env support for backend LLM provider config (python-dotenv; committed .env.example, gitignored .env) | 2026-07-08 | 2d2510b | [260708-e7z-add-env-support-for-backend-llm-provider](./quick/260708-e7z-add-env-support-for-backend-llm-provider/) |
| 260708-jov | Make Gemini parse_constraints reliable (system instruction, keeps AUTO/NLC-03) + load .env in conftest so `-m live` works from .env; live parity test now passes against real Gemini | 2026-07-08 | 734a146 | [260708-jov-make-gemini-parse-constraints-reliable-s](./quick/260708-jov-make-gemini-parse-constraints-reliable-s/) |
| 260709-m9m | Map LLM provider errors → clean 503 (neutral `LLMProviderError`, no vendor exception crosses the seam) instead of bare 500; also scoped conftest `.env` load to GEMINI_API_KEY only so a dev's `LLM_PROVIDER=gemini` no longer breaks stub-default tests | 2026-07-09 | 8d0c785 | [260709-m9m-map-llm-provider-errors-to-a-clean-503-i](./quick/260709-m9m-map-llm-provider-errors-to-a-clean-503-i/) |
| 260713-o5e | Add `@pytest.mark.live` tests covering all LLMProvider ops vs real Gemini: `generate_insights` now runs the real D-06 grounding guard (regression net for insight-api-502-ungrounded), and live `parse_constraints` parity broadened to scale_demand/set_max_hours | 2026-07-13 | 1623dae | [260713-o5e-add-pytest-mark-live-tests-covering-all-](./quick/260713-o5e-add-pytest-mark-live-tests-covering-all-/) |
| 260713-pn3 | Register `openrouter` as a third selectable LLMProvider (openai SDK against OpenRouter's OpenAI-compatible API), mirroring GeminiLLMProvider's contract exactly, so a dev can set `LLM_PROVIDER=openrouter` locally to avoid Gemini's 50-req/day free-tier quota during testing; keyless-default-CI invariant (stub) untouched | 2026-07-13 | ee156bd | [260713-pn3-add-openroute-as-default-provider-gemini](./quick/260713-pn3-add-openroute-as-default-provider-gemini/) |
| 260713-stq | Verified user's real OPENROUTER_API_KEY works; swapped `_OPENROUTER_DEFAULT_MODEL` from `meta-llama/llama-3.3-70b-instruct:free` (upstream 429) to live-verified `openai/gpt-oss-20b:free`. Non-live suite stays green (123 passed); 1 of 2 live OpenRouter tests pass — the other surfaced an unrelated pre-existing grounding-guard gap (see Blockers/Concerns), reported not silently fixed | 2026-07-13 | 77134de | [260713-stq-swap-openrouter-default-model-to-openai-](./quick/260713-stq-swap-openrouter-default-model-to-openai-/) |
| 260714-owo | Added throwaway `data/sample_tiny_input_more_tm.json` fixture (superset of `sample_tiny_input.json`) with 12 new qualified+rostered Team Members for task 99260066-B32A-423D-97A1-8A649BABBAAD, raising qualified-member coverage from a sub-3 ceiling to a floor of 4 across all 98 demanded hourly buckets — built to test whether more staff supply lets `set_min_workers_per_task n=3` actually become satisfiable in round-2 of the CP-SAT solve (previously stuck at 0/98 hours even at OPTIMAL/300s) | 2026-07-14 | c7709ff | [260714-owo-create-a-new-data-fixture-variant-of-dat](./quick/260714-owo-create-a-new-data-fixture-variant-of-dat/) |
| 260715-hm2 | Fixed `set_max_hours` override penalty scaling bug in `engine/cpsat/builder.py`'s `round2_cost`: the `over` overflow var is VOL_SCALE-scaled (hundredths-of-hour) but was multiplied directly by `MAX_HOURS_PENALTY` with no division back out, silently inflating the real penalty ~100x beyond the documented $1,000/hour (empirically found via live API testing: a 24.62h-over-cap override produced a ~$2.46M cost delta instead of the intended ~$24,620). Fix: `(C.MAX_HOURS_PENALTY // C.VOL_SCALE) * sum(maxh_terms)`. Full suite (124 tests) green | 2026-07-15 | 5bf1689 | [260715-hm2-fix-set-max-hours-penalty-scaling-bug-in](./quick/260715-hm2-fix-set-max-hours-penalty-scaling-bug-in/) |
| 260715-vel | Retired `docs/` as a planning tracker and split it by lifecycle, closing the drift left by adopting GSD mid-project (phases 1–2 were hand-documented; `docs/` unmaintained since Phase 3). Deleted `docs/PLAN.md` (superseded by `.planning/`; its 5 deferred follow-ups migrated to `todos/pending/` in a84ddec first, so zero loss). Fixed `docs/API.md` — it was missing the entire LLM layer and is about to be the contract v0.4's frontend is written against; added `POST /constraints` + `GET /runs/{id}/insights` + `LLM_PROVIDER`, verified against source (caught that insights fails **502** not 503, and the not-ready case is a deliberate **200 `ready:false`** not 409). Trimmed `design.md` to the durable "why", fixing two inverted claims (provider diagram said "Claude now; Gemini later" — reality is stub-default + Gemini + OpenRouter, Claude never built; deploy said Render — reality is AWS) and folding in the shipped LLM-layer design as §4. Archived phase-1/2 docs via `git mv` (history intact); froze `vision.md` in place as the permanent origin snapshot (1-line diff); added `docs/README.md` stating the one-owner-per-audience boundary so the drift can't silently recur. Fixed PROJECT.md's false `docs/decisions/` ADR claim (no ADR system created). Docs-only — `git diff -- backend/` empty | 2026-07-15 | 0729b21 | [260715-vel-retire-docs-as-planning-tracker-split-by](./quick/260715-vel-retire-docs-as-planning-tracker-split-by/) |

### Roadmap Evolution

- Phase 4 edited: reworded Claude-specific title/goal/criteria to provider-generic (free-tier LLM, Gemini first); also updated REQUIREMENTS LLM-02/TEST-04
- v0.4 roadmap added: 4 phases, 24/24 v1 requirements mapped, no orphans, no duplicates. Initially numbered 5-8 (continuing v0.3), then **renumbered to 1-4** on operator instruction — phase numbering now restarts per milestone.

## Deferred Items

Items acknowledged and deferred at milestone close on 2026-07-15:

| Category | Item | Status | Deferred At |
|----------|------|--------|-------------|
| debug | knowledge-base (running KB log of resolved sessions; audit flags it as open due to no explicit closed status) | unknown | v0.3 close (2026-07-15) |
| todo | 2026-06-29-harden-scenario-fixture-path-against-traversal.md (api) | pending | v0.3 close (2026-07-15) |
| todo | 2026-07-09-demand-deadline-scheduling-instead-of-flat-hourly.md (engine) | pending | v0.3 close (2026-07-15) |
| todo | 2026-07-09-extract-engine-as-separate-service.md (architecture) | pending | v0.3 close (2026-07-15) |

## Session Continuity

Last session: 2026-07-19T14:28:45.237Z
Stopped at: Phase 04 UI-SPEC approved
Resume file: .planning/phases/04-results-insights/04-UI-SPEC.md

## Operator Next Steps

- Execute the planned phase with `/gsd-execute-phase 1` — 7 plans across 5 waves
- `01-02-PLAN.md` is a **blocking human checkpoint** (npm package legitimacy gate) and runs in Wave 1 — execution pauses there for your approval before any package is installed
- Phases 2-4 are all UI-bearing (`UI hint: yes` in ROADMAP.md) — `/gsd-ui-phase` is available for a design contract before planning each

</content>
