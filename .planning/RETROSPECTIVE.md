# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — LLM Layer

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

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | multiple | 4 | Established vertical-slice MVP roadmap (stub-first, real-provider-last); introduced plan-time STRIDE threat modelling and coverage-block UAT classification |

### Cumulative Quality

| Milestone | Tests | Coverage | Zero-Dep Additions |
|-----------|-------|----------|---------------------|
| v1.0 | 124 (non-live) + 1 gated live | — | `google-genai`, OpenAI SDK (OpenRouter) |

### Top Lessons (Verified Across Milestones)

1. Calibrate penalty/weight constants as soon as they're introduced, not deferred to a later phase.
2. Pair relative-behavior tests with at least one absolute-magnitude assertion for anything scaling a raw constant.
