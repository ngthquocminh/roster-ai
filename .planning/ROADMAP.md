# Roadmap: ShiftMind — Phase 3 LLM Layer

## Overview

This milestone adds the natural-language layer on top of the already-built CP-SAT
engine (Phase 1) and FastAPI/SQLite backend (Phase 2). It is structured as four
vertical slices, each shippable and end-to-end testable. Slice 1 proves the
LLM→solver seam by driving one plain-English constraint all the way through:
submit text → validate → store as a soft override → CP-SAT applies it as a soft
penalty → re-solve → the returned schedule reflects it, all driven by a stubbed
provider with no live API. Slice 2 broadens to the full five-tool set with safe
argument/ID validation and parse-UX fields. Slice 3 adds the decoupled on-demand
insight report. Slice 4 drops the real Claude provider in behind the Protocol and
calibrates penalty weights — while CI stays stub-only throughout.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: First NL Constraint End-to-End** - One plain-English constraint flows through the stub provider into a soft CP-SAT penalty and re-solve, proving the seam (completed 2026-06-28)
- [ ] **Phase 2: Full 5-Tool Set + Safe Validation** - All five solver tools, with arg/ID validation, plain-English errors, and parse-UX fields
- [ ] **Phase 3: On-Demand Insight Reports** - Decoupled, metric-grounded, cached natural-language insight endpoint
- [ ] **Phase 4: Real Claude Provider + Penalty Calibration** - Live Claude behind the Protocol, calibrated weights, one CI-excluded integration test

## Phase Details

### Phase 1: First NL Constraint End-to-End

**Goal**: A user submits one plain-English constraint and gets back a re-solved schedule that honors it — the stub provider parses the text into a soft override, the override is stored, CP-SAT applies it as a soft penalty, and the scenario re-solves to a schedule that reflects it.
**Mode:** mvp
**Depends on**: Nothing (engine + backend from Phases 1–2 already built)
**Requirements**: ENG-01, ENG-02, ENG-03, ENG-06, LLM-01, LLM-03, NLC-01, NLC-06, TEST-01, TEST-02
**Success Criteria** (what must be TRUE):

  1. A POST to the parse-constraints endpoint with plain-English text returns 200 and persists a soft override with a stable per-override id to the scenario `overrides` JSON.
  2. Re-solving a scenario that carries an override returns a schedule that visibly honors it; the override enters the round-2 (cost) objective as a soft penalty only — never round-1 (unmet), and never as a hard constraint that can make the model infeasible.
  3. A scenario with no overrides re-solves identically to the pre-LLM baseline (no regression).
  4. The `StubLLMProvider` is injected via a `get_llm_provider` dependency (mirroring `get_engine`) and returns Claude-faithful `tool_use` blocks (`type`/`id`/`name`/`input`); the full NL→override→re-solve round trip passes in CI with zero network calls.

**Plans**: 3/3 plans complete

- [x] 01-01-PLAN.md — Engine soft-penalty slice: OverrideCall domain seam + SolverConfig.overrides + CP-SAT per-hour shortfall penalty (round-2 only) + engine honors/no-regression tests
- [x] 01-02-PLAN.md — Parse/store slice: vendor-agnostic LLMProvider + StubLLMProvider + get_llm_provider + POST /constraints + constraint_service (resolve/validate/persist) + ScenarioRepo.update_overrides
- [x] 01-03-PLAN.md — Integration slice: run_service threads overrides into SolverConfig + full stub-driven NL→override→re-solve round-trip test

### Phase 2: Full 5-Tool Set + Safe Validation

**Goal**: A user can express any of the five supported constraints in plain English, see a readable echo of what was understood, and have unsafe, degenerate, or unknown inputs rejected with clear guidance before anything reaches the solver.
**Mode:** mvp
**Depends on**: Phase 1
**Requirements**: NLC-02, NLC-03, NLC-04, NLC-05, VAL-01, VAL-02, VAL-03, ENG-05, TEST-03
**Success Criteria** (what must be TRUE):

  1. Each of the five tools (`lock_worker_shift`, `set_min_workers_per_task`, `exclude_worker_from_task`, `scale_demand`, `set_max_hours`) can be produced from NL text and applied; the response echoes a human-readable `parsed_constraint` summary of what was understood.
  2. Text that maps to no tool returns "no constraint found", and ambiguous/unparseable text returns a `clarification_needed` signal with a question (single-turn) — neither path forces a spurious tool call.
  3. Out-of-bounds args (`scale_demand` ≤ 0, `set_max_hours` = 0, negatives) and unknown member/task references are rejected with a plain-English error naming the offending reference/argument and listing the valid options — no hallucinated id or degenerate arg ever reaches the solver.
  4. A re-solve whose coverage collapses to zero for a task family is detected and flagged, rather than narrated as an optimization success.
  5. Validation tests cover unknown IDs and out-of-bounds arguments, including a mixed multi-tool call where one reference is valid and one is not.

**Plans**: 4 plans

- [ ] 02-01-PLAN.md — Partial-apply contract + parse-UX backbone (response shape, _resolve_member, no_constraint_found/clarification/rejection) for the min-workers tool
- [ ] 02-02-PLAN.md — Full five-tool set: stub regexes + per-tool validation + scale_demand pre-solve reshape + lock/exclude/max_hours soft round-2 penalties + real-engine honor tests
- [ ] 02-03-PLAN.md — Degenerate-solve detection: SolveResult.warnings + zero-coverage flag through serialization (ENG-05)
- [ ] 02-04-PLAN.md — TEST-03 validation suite: unknown IDs, out-of-bounds args, and mixed valid/invalid multi-tool calls

### Phase 3: On-Demand Insight Reports

**Goal**: A user can fetch a natural-language insight report for a completed run that cites the run's real metric values, generated as a separate on-demand step that can never invalidate a successfully computed schedule.
**Mode:** mvp
**Depends on**: Phase 1 (run results exist); independent of Phase 2
**Requirements**: INS-01, INS-02, INS-03, INS-04
**Success Criteria** (what must be TRUE):

  1. A GET on the insights endpoint for a COMPLETED run returns a natural-language report; the same call for a not-yet-completed run returns a clear not-ready response.
  2. Every number in the report appears verbatim in the run's metrics JSON — no fabricated figures and no generic "coverage was adequate" language.
  3. Forcing the provider to fail leaves the run status COMPLETED and the schedule result untouched; only the insight call returns an error.
  4. A second fetch returns the cached `runs.insight_json` without re-calling the provider.

**Plans**: TBD

### Phase 4: Real Claude Provider + Penalty Calibration

**Goal**: The real Claude provider drops in behind the `LLMProvider` Protocol with a config-driven model id, override penalty weights are empirically calibrated against the committed full-week fixture, and a live integration test confirms wire-format parity — while the default CI run stays stub-only and needs no API key.
**Mode:** mvp
**Depends on**: Phases 1–3
**Requirements**: LLM-02, ENG-04, TEST-04
**Success Criteria** (what must be TRUE):

  1. Setting `ANTHROPIC_MODEL` selects the Claude model (default `claude-sonnet-4-6`); switching the configured provider from stub to claude requires no changes to service or route code (the seam holds).
  2. Override penalty weights are calibrated against the committed full-week fixture so a satisfiable override is honored while an unsatisfiable one degrades gracefully to baseline coverage — respected, but not dominating the round-2 cost objective.
  3. One live-Claude integration test exercises the same parse code path as the stub and confirms `tool_use` wire-format parity; it is excluded from the default CI run, which stays green with no API key present.

**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. First NL Constraint End-to-End | 3/3 | Complete    | 2026-06-28 |
| 2. Full 5-Tool Set + Safe Validation | 0/4 | Not started | - |
| 3. On-Demand Insight Reports | 0/TBD | Not started | - |
| 4. Real Claude Provider + Penalty Calibration | 0/TBD | Not started | - |
