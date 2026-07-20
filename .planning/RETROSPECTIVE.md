# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v0.3 — LLM Layer

**Shipped:** 2026-07-15
**Phases:** 4 | **Plans:** 12 | **Tasks:** 19

### What Was Built
- `LLMProvider` Protocol (parse_constraints + generate_insights) with a `StubLLMProvider` driving all default CI, so the full NL → override → re-solve round trip is testable with zero network calls
- All five solver-hook tools (`lock_worker_shift`, `set_min_workers_per_task`, `exclude_worker_from_task`, `scale_demand`, `set_max_hours`) parsed from plain English with partial-apply validation, plain-English rejection errors, and clarification-needed handling
- A decoupled, cached, metric-grounded on-demand insight report endpoint (`GET /runs/{id}/insights`) — provider failure never invalidates a completed schedule (D-06 grounding guard rejects fabricated numbers)
- Two real, network-backed LLM providers (`GeminiLLMProvider`, `OpenRouterLLMProvider`) behind the same seam, config-selected via `LLM_PROVIDER`, with calibrated override penalty weights and a CI-excluded live parity test

### What Worked
- The provider-neutral `to_override_call` translation boundary (D-07/D-08) meant adding a second and third real provider (Gemini, then OpenRouter) required zero changes to `constraint_service`, routes, or validation — the seam held exactly as designed from Phase 1
- Soft-penalty-only override application (never round-1, never a hard constraint) meant every new tool added in Phase 2 was a drop-in extension of the same CP-SAT pattern, with no risk of infeasibility regressions
- Keeping insight generation as a separate, decoupled post-run step (Phase 3) paid off directly in Phase 4 — LLM provider swaps and calibration work never had to reason about schedule-invalidation risk

### What Was Inefficient
- Penalty weight calibration (ENG-04) was deferred past its natural landing point in Phase 1/2 and required a dedicated sweep harness + full-week-fixture empirical pass in Phase 4; the initial `MIN_WORKERS_PENALTY = 100_000` placeholder lived uncalibrated for three phases
- The `04-03` calibration regression tests were originally written against the full-week fixture with a fixed time limit, which is not safe against CP-SAT's non-deterministic parallel portfolio search — this caused a flaky/slow test file that had to be rebased onto small hand-built deterministic problems mid-milestone
- A `set_max_hours` penalty scaling bug (VOL_SCALE double-application, ~100x cost inflation) shipped silently through Phase 2's tests and was only caught by live API testing in a post-phase-4 quick task — no test asserted the actual dollar magnitude of the penalty, only its relative ordering
- The D-06 grounding guard's `coverage_by_day` dict-KEY blind spot (rejecting faithful "Day 0" citations) was invisible for the entire milestone because no live provider run had reached the guard with a real completion until a quick task after Phase 4 closed

### Patterns Established
- Provider-neutral translation boundary: no vendor payload (Claude tool_use dict, Gemini FunctionCall, OpenRouter tool_call) may cross into `domain.OverrideCall` except through `llm/translate.to_override_call`
- Config-driven factory selection mirroring `engine/base.py`'s `create_engine` lazy-import registry, applied identically to `llm/base.py`'s `create_provider`
- Secrets (`llm_api_key`, `openrouter_api_key`) always declared `repr=False` on `Settings` and passed only as constructor kwargs — never logged, persisted, or interpolated into any string
- STRIDE threat modelling authored at plan time (`<threat_model>` block in PLAN.md) enables a fast, grep-depth ASVS-1 security short-circuit at phase close instead of a full retroactive audit

### Key Lessons
1. Penalty/weight calibration for a soft-constraint solver should be scheduled as its own phase-scoped task as soon as the first penalty constant is introduced, not deferred to "whenever the real provider lands" — three phases of uncalibrated placeholders is a long window for a silent scaling bug to hide in.
2. Tests that assert relative behavior (an override is "honored", a solve stays "OPTIMAL") should be paired with at least one test asserting absolute magnitude (the dollar cost is in the right order), especially for anything that scales a raw penalty constant — relative-only tests let a 100x scaling bug pass clean.
3. Any code path that only executes against a live LLM response (grounding guards, response parsers) needs a live-provider test earlier than "whenever a quick task happens to touch it" — two separate D-06 grounding-guard gaps in this milestone were only surfaced by live traffic weeks after their originating phase closed.

### Cost Observations
- Sessions: multiple across ~6 weeks (2026-05-30 project start → 2026-07-15 ship)
- Notable: several post-phase-4 quick tasks (OpenRouter provider addition, live-test hardening, penalty bug fix) extended real-world validation past the formal phase boundary — live-provider testing surfaced defects that stub-only CI could not

---

## Milestone: v0.4 — Frontend (React UI)

**Shipped:** 2026-07-20
**Phases:** 4 | **Plans:** 28

### What Was Built
- Vite + React 19 + TypeScript app under `frontend/`, with a fully OpenAPI-codegen'd typed client (`openapi-typescript` + `openapi-fetch`) — zero hand-authored request/response shapes anywhere in `src/api/`
- CORS-enabled FastAPI backend (env-driven allow-list, no wildcard/credentials) and a persistent 4-route nav shell (Home, ScenarioEditor, RunHistory, ResultsView) with deep-linkable routes and honestly-labelled placeholders retired as each real view landed
- ScenarioEditor: applied-overrides list + a plain-English constraint transcript rendering all five `POST /constraints` outcomes (applied, rejected, mixed, clarification, provider-down) with visually distinct treatments — never raw tool-call JSON
- RunHistory: trigger a run, self-terminating poll to a terminal state, an honest non-cancelable in-flight wait, and prior-run history with inline `FAILED` error text
- ResultsView: null-safe coverage cards, a demand-vs-served chart (with an honest empty state), a schedule table, and an on-demand insight report that branches on the response's `ready` field — never the HTTP status code — with 502 failures isolated from the rest of the view

### What Worked
- The byte-identical query-key invalidation contract (writer mutation key === reader query key) held cleanly across all 4 phases and was independently confirmed by the milestone's cross-phase integration check — zero silent-cache-miss bugs
- Reusing the blocking human-verify checkpoint pattern for both supply-chain legitimacy (`[SUS]`/`[SLOP]` npm package review — Phase 1 for the initial toolchain, Phase 4 for `recharts`) and for UX/visual outcome-treatment review (Phase 2's five-outcome transcript) scaled well with zero process friction on reuse
- Skipping a dedicated research phase (React SPA over an already-documented REST API judged well-trodden) produced zero rework — open choices (charting library, polling strategy, client typing approach) were resolved cleanly at plan-phase time as anticipated
- The enabled-gated dependent-query pattern (`useOverrides`, `useRunResult`) — never fetching a child resource until its parent query resolves — was established once and reused identically in Phases 2 and 4 with no adaptation needed

### What Was Inefficient
- Two of four phases (3 and 4) required a re-verification cycle after live UAT surfaced a real gap that automated tests had missed: Phase 3's `RunHistoryTable` timestamp columns overflowed because test fixtures used short, whole-second, `Z`-suffixed timestamps (`"2026-07-18T10:00:00Z"`, 20 chars) instead of the real 32-character microsecond+offset ISO format the backend actually emits (`_now()`'s `datetime.now(timezone.utc).isoformat()`); Phase 4's `DemandVsServedChart` rendered a blank, unlabelled chart box for a zero-demand run because no plan or test modeled the empty-`coverage_by_function` case at all
- Both gaps share the same root shape as a v0.3 lesson (see Top Lessons below): the defect was invisible to unit/component tests using simplified stand-in data and was only caught once a live UAT pass exercised the feature against a real triggered run

### Patterns Established
- Query-key byte-identity as an explicit, checkable contract between a mutation's `invalidateQueries` call and the query it must refresh — documented per-hook and grep-verifiable rather than merely "the same string typed twice"
- `enabled`-gated TanStack Query dependent queries as the standard mechanism for parent→child data dependencies (scenario→overrides, run→result), replacing any need for manual loading-state chaining
- Structural isolation for non-critical async operations (the insight-report mutation carries no `queryClient.invalidateQueries` call at all) so a failure in one surface can never invalidate or block an already-successful adjacent surface
- Reusable blocking human-verify checkpoint plans for both supply-chain review and end-of-phase visual/UX review, run as the final wave of a phase rather than folded into implementation plans

### Key Lessons
1. Test fixtures must model the real backend's exact output shape — string length, precision, format — not a simplified stand-in; a 20-char test timestamp against a 32-char real one is what let Phase 3's column-overflow bug reach live UAT undetected.
2. Every "populated" data-rendering component needs an explicit empty/zero-state test as a first-class item in its plan's test list, not an afterthought — Phase 4's blank chart box for a zero-demand run was a genuine coverage gap in the original plan, not a regression from working code.
3. A live/UAT verification pass (not just unit/component tests against synthetic fixtures) remains the most reliable way to catch defects in exactly the class of code that only breaks under real data shape — consistent with the v0.3 finding about live-provider LLM testing.

### Cost Observations
- Sessions: multiple across 5 days (2026-07-15 → 2026-07-20)
- Model mix: adaptive profile (haiku for lightweight agent tasks e.g. integration checker, sonnet/opus for planning and execution)
- Notable: both re-verification cycles (Phase 3, Phase 4) were triggered by dedicated live UAT passes using claude-in-chrome against a real running backend+frontend — this milestone is the first to use live browser automation for UAT rather than relying solely on human-reported verification

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v0.3 | multiple | 4 | Established vertical-slice MVP roadmap (stub-first, real-provider-last); introduced plan-time STRIDE threat modelling and coverage-block UAT classification |
| v0.4 | multiple | 4 | First frontend milestone; introduced live browser-automation UAT (claude-in-chrome) which caught 2 real gaps (G-03-1, G-04-4) that synthetic-fixture tests missed |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|---------------------|
| v0.3 | 124 (non-live) + 1 gated live | — | `google-genai`, OpenAI SDK (OpenRouter) |
| v0.4 | 237 frontend (vitest) + 137 backend (pytest, unchanged) | — | `recharts` (sole new frontend runtime dep beyond the Phase 1 scaffold) |

### Top Lessons (Verified Across Milestones)

1. Calibrate penalty/weight constants as soon as they're introduced, not deferred to a later phase.
2. Pair relative-behavior tests with at least one absolute-magnitude assertion for anything scaling a raw constant.
3. Test fixtures and synthetic data must model the real system's actual output shape (format, length, precision) — both milestones independently found defects (v0.3's D-06 grounding-guard gaps, v0.4's timestamp-overflow and empty-chart gaps) that were invisible to tests using simplified stand-in data and were only caught by live/UAT verification against real output.
