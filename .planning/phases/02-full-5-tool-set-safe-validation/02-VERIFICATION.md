---
phase: 02-full-5-tool-set-safe-validation
verified: 2026-06-29T00:00:00Z
status: passed
score: 5/5 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 2: Full 5-Tool Set + Safe Validation — Verification Report

**Phase Goal:** A user can express any of the five supported constraints in plain English, see a readable echo of what was understood, and have unsafe, degenerate, or unknown inputs rejected with clear guidance before anything reaches the solver.
**Verified:** 2026-06-29
**Status:** PASSED
**Re-verification:** No — initial verification

---

## Goal Achievement

### Observable Truths (Roadmap Success Criteria)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| SC-1 | Each of the five tools (lock_worker_shift, set_min_workers_per_task, exclude_worker_from_task, scale_demand, set_max_hours) can be produced from NL text and applied; the response echoes a human-readable parsed_constraint summary | VERIFIED | Five regex patterns in llm/stub.py; five elif branches in constraint_service.parse_and_store; parsed_constraint wording in each branch; four passing API round-trip tests (test_scale_demand_applied, test_lock_worker_shift_applied, test_exclude_worker_from_task_applied, test_set_max_hours_applied) plus pre-existing set_min_workers tests |
| SC-2 | Text that maps to no tool returns "no constraint found"; ambiguous/unparseable text returns a clarification_needed signal with a question — neither path forces a spurious tool call | VERIFIED | no_constraint_found logic: `not tool_calls and clarification_needed is None`; _PARTIAL_WORKERS_RE emits _clarification sentinel; tests test_no_constraint_found_in_text_returns_200_with_flag, test_partial_phrasing_clarification, test_ambiguous_task_token_returns_clarification_needed all pass |
| SC-3 | Out-of-bounds args (scale_demand ≤ 0, set_max_hours = 0, negatives) and unknown member/task references are rejected with a plain-English error naming the offending reference/argument and listing the valid options — no hallucinated id or degenerate arg ever reaches the solver | VERIFIED | Service validates factor>0, max_hours>0, day in 0..horizon; _resolve_task/_resolve_member emit "Unknown task/member {token!r}. Valid tasks/members: {list}" on zero-match; tests test_unknown_task_rejected, test_unknown_member_rejected, test_scale_demand_bad_factor, test_max_hours_zero_rejected, test_lock_out_of_horizon_day_rejected, test_rejection_error_names_ref all pass; mixed multi-tool tests confirm only valid entries are persisted |
| SC-4 | A re-solve whose coverage collapses to zero for a task family is detected and flagged, rather than narrated as an optimization success | VERIFIED | SolveResult.warnings: List[str] = field(default_factory=list) in domain/result.py; detection loop in engine.py (lines 117-123) appends warning when stat.required_h > 1e-9 and stat.served_h <= 1e-9 without touching status; serialize_result includes "warnings": r.warnings; 14 tests in test_engine_degenerate.py all pass |
| SC-5 | Validation tests cover unknown IDs and out-of-bounds arguments, including a mixed multi-tool call where one reference is valid and one is not | VERIFIED | test_unknown_task_rejected, test_unknown_member_rejected, test_rejection_error_names_ref, test_scale_demand_bad_factor, test_mixed_valid_invalid_multi_tool, test_mixed_valid_oob_multi_tool all pass; non-persistence verified via idempotent re-submit in each test |

**Score: 5/5 truths verified** (0 present-behavior-unverified)

---

### Plan-Level Must-Have Truths (all 21 verified)

#### Plan 02-01 (6 truths)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | POST /constraints returns 200 with a structured body {applied[], rejected[], clarification_needed, no_constraint_found} for every non-404 request | VERIFIED | ConstraintParseResponse in api/schemas.py; test_post_constraints_response_has_structured_body passes |
| 2 | Text with no recognizable constraint shape returns no_constraint_found=true, 200 | VERIFIED | Service logic `no_constraint_found = (not tool_calls and clarification_needed is None)`; test_no_constraint_found_in_text_returns_200_with_flag passes |
| 3 | Ambiguous/partial constraint text returns clarification_needed with a question, 200 | VERIFIED | _PARTIAL_WORKERS_RE sentinel + _resolve_task multi-match path; test_partial_phrasing_clarification + test_ambiguous_task_token_returns_clarification_needed pass |
| 4 | An unknown member or task reference is rejected with a plain-English error naming the offending token AND listing the valid options, via _resolve_member/_resolve_task | VERIFIED | Both helpers return `error=f"Unknown task/member {token!r}. Valid tasks/members: {valid_names}"`; test_rejection_error_names_ref asserts both token and "Valid tasks:"/"Valid members:" appear |
| 5 | applied[], rejected[], and clarification_needed can be non-null together in one response | VERIFIED | test_mixed_applied_and_clarification: "at least 2 on C Pick and more people on packing" yields 1 applied + clarification_needed |
| 6 | Each applied entry carries a human-readable parsed_constraint string | VERIFIED | All five tool branches set parsed_constraint; test_post_constraints_parsed_constraint_is_string + four tool-specific tests confirm non-empty string |

#### Plan 02-02 (6 truths)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | All five tools can be produced from NL text, validated, and applied | VERIFIED | Four new API round-trip tests pass; test_multi_tool_applied confirms two applied entries from one sentence |
| 2 | scale_demand multiplies demand bands pre-solve in _aggregate_demand; unmet slack absorbs any shortfall | VERIFIED | builder.py lines 115-137: scale dict from overrides multiplied at both INDIRECT (hc) and direct (vol) accumulation points; test_scale_demand_honored passes with real CP-SAT (factor=8.0 forces 2 members) |
| 3 | lock_worker_shift, exclude_worker_from_task, set_max_hours add bounded soft penalties to round2_cost only — never round-1, never hard constraints | VERIFIED | builder.py lines 360-404: lock_terms/excl_terms/maxh_terms all summed into round2_cost only; test_lock_worker_shift_stays_feasible, test_exclude_worker_from_task_honored, test_set_max_hours_honored all pass |
| 4 | Each new tool produces a human-readable parsed_constraint echo | VERIFIED | Four parsed_constraint strings in constraint_service.py: "Scale demand for {label} by {factor}x", "Keep {name} scheduled on day {day}", "Exclude {name} from {label}", "Cap {name} at {max_hours} hours per week (soft)" |
| 5 | Per-tool arg bounds validated before persistence; failures land in rejected[] naming the arg and listing valid options | VERIFIED | factor>0, max_hours>0, day in 0..horizon_h//24-1 all checked; test_scale_demand_bad_factor_rejected, test_max_hours_zero_rejected, test_lock_out_of_horizon_day_rejected pass |
| 6 | A scenario with no overrides still re-solves identically to the pre-LLM baseline (no regression) | VERIFIED | test_no_regression_empty_overrides passes with real CP-SAT engine |

#### Plan 02-03 (4 truths)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | SolveResult carries a warnings: list[str] field defaulting to empty | VERIFIED | domain/result.py line 53: `warnings: List[str] = field(default_factory=list)` as last field; test_warnings_field_present_on_solve_result passes |
| 2 | A re-solve where a task family with positive demand has zero assigned supply is detected and surfaced as a warning naming the family | VERIFIED | engine.py lines 117-123: detection loop after coverage_by_function assembly; test_degeneracy_detected_on_zero_supply confirms 1 warning naming family + hours |
| 3 | Detection runs post-solve and never alters solver_status or fails the run | VERIFIED | engine.py: status = lex.status set before detection loop; warnings is a separate list; test_status_not_altered_when_warnings_present confirms status unchanged |
| 4 | warnings survive serialization into runs.result_json | VERIFIED | serialize.py line 44: `"warnings": r.warnings`; test_warnings_in_serialize_result_output and test_warnings_values_survive_serialization pass |

#### Plan 02-04 (5 truths)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Validation tests cover unknown task references and unknown member references (each rejected, 200, naming the token and listing valid options) | VERIFIED | test_unknown_task_rejected (GHOST_TASK_NONEXISTENT in error), test_unknown_member_rejected, test_rejection_error_names_ref ("Valid tasks:"/"Valid members:" in error) |
| 2 | Validation tests cover out-of-bounds args (factor<=0, max_hours=0, negatives) — each rejected naming the arg | VERIFIED | test_scale_demand_bad_factor (factor=0 via "boost C Pick volume by 0x"), test_scale_demand_bad_factor_rejected, test_max_hours_zero_rejected; "factor" / "max_hours" in rejection error asserted |
| 3 | A mixed multi-tool call where one reference is valid and one is unknown yields applied[]+rejected[] in one 200 response; only valid one persists | VERIFIED | test_mixed_valid_invalid_multi_tool: "at least 2 on C Pick and exclude XYZ_NONEXISTENT_MEMBER from C Pick" -> applied[0] (set_min_workers), rejected[0] (unknown member); re-submit confirms idempotent applied id |
| 4 | A mixed multi-tool call where one tool is valid and one has an out-of-bounds arg yields applied[]+rejected[] in one 200 response | VERIFIED | test_mixed_valid_oob_multi_tool: "at least 3 on C Pick and boost C Pick volume by 0x" -> applied[0] (set_min_workers), rejected[0] (factor error); re-submit confirms idempotent applied id |
| 5 | All TEST-03 cases run against StubLLMProvider + StubEngine via app.dependency_overrides with zero network calls | VERIFIED | client fixture injects both overrides; StubLLMProvider is the production-grade deterministic stub; no live API called |

---

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/api/schemas.py` | AppliedConstraint, RejectedConstraint, reshaped ConstraintParseResponse | VERIFIED | All three models present; ConstraintParseResponse has applied, rejected, clarification_needed, no_constraint_found |
| `backend/api/routers/constraints.py` | Only LookupError->404; no ValueError->400 | VERIFIED | router only catches LookupError; comment confirms ValueError path removed |
| `backend/services/constraint_service.py` | _ResolveResult NamedTuple, _resolve_task, _resolve_member, partial-apply parse_and_store with all 5 tools | VERIFIED | All symbols present and substantive; 381 lines of real implementation |
| `backend/llm/stub.py` | _split_fragments, _SPLIT_RE, _MIN_WORKERS_RE, _PARTIAL_WORKERS_RE, _SCALE_DEMAND_RE, _LOCK_SHIFT_RE, _EXCLUDE_RE, _MAX_HOURS_RE, _DAY_MAP | VERIFIED | All patterns and helpers present; parse_constraints dispatches through all 5 tools plus clarification sentinel |
| `backend/config/constants.py` | LOCK_SHIFT_PENALTY, EXCLUDE_WORKER_PENALTY, MAX_HOURS_PENALTY | VERIFIED | All three present at lines 46, 52, 58 with explanatory comments |
| `backend/engine/cpsat/builder.py` | scale dict in _aggregate_demand; lock/exclude/maxh elif branches in _build_objectives | VERIFIED | scale dict at lines 115-117; elif chain at lines 360-404; all terms into round2_cost only |
| `backend/domain/result.py` | warnings: List[str] = field(default_factory=list) on SolveResult | VERIFIED | Present as last field; frozen=False to allow field(default_factory) |
| `backend/engine/cpsat/engine.py` | Post-solve zero-coverage detection loop; warnings passed to SolveResult | VERIFIED | Detection loop at lines 117-123; SolveResult constructed with warnings= at line 125 |
| `backend/services/serialize.py` | "warnings": r.warnings in serialize_result output | VERIFIED | Line 44: `"warnings": r.warnings` |
| `backend/tests/test_engine_degenerate.py` | 14 degeneracy detection tests | VERIFIED | File exists; 14 test functions covering field presence, detection, negative cases, edge cases, status invariant, serialization |
| `backend/tests/test_engine_overrides.py` | 5 real-CP-SAT honor + no-regression tests | VERIFIED | File exists; test_no_regression_empty_overrides, test_scale_demand_honored, test_exclude_worker_from_task_honored, test_set_max_hours_honored, test_lock_worker_shift_stays_feasible |
| `backend/tests/test_constraints_api.py` | Full TEST-03 validation suite (36 tests total) | VERIFIED | 36 tests covering all NLC/VAL/TEST-03 criteria; includes 5 new TEST-03 functions from plan 02-04 |

---

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `llm/stub.py` | `services/constraint_service.py` | OverrideCall list returned by parse_constraints, consumed by parse_and_store | VERIFIED | _to_override_call builds provider-neutral OverrideCall; service receives list[OverrideCall] and dispatches on tool name |
| `services/constraint_service.py` | `api/routers/constraints.py` | parse_and_store returns dict; router wraps in ConstraintParseResponse via response_model | VERIFIED | Router calls parse_and_store, catches only LookupError->404; FastAPI serializes dict to ConstraintParseResponse |
| `engine/cpsat/builder.py` | `engine/cpsat/engine.py` | CpSatBuilder.build() consumes self.overrides; engine passes config.overrides to builder | VERIFIED | engine.py line 26: `CpSatBuilder(problem, overrides=config.overrides).build()` |
| `services/serialize.py` | `domain/result.py` | serialize_result reads r.warnings from SolveResult | VERIFIED | serialize.py line 44 directly accesses r.warnings |
| `services/constraint_service.py` | `store/repositories.py` | Only applied entries written via repo.update_overrides + conn.commit | VERIFIED | Lines 368-373: reads existing overrides, merges applied entries only, calls update_overrides |

---

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|--------------|--------|-------------------|--------|
| `constraint_service.parse_and_store` | applied, rejected, clarification_needed | provider.parse_constraints(text) -> _resolve_task/_resolve_member against real fixture | Yes — resolves against loaded SchedulingProblem from fixture file | FLOWING |
| `builder._aggregate_demand` | scale dict | self.overrides filtered by tool=="scale_demand" | Yes — real override args from scenario DB | FLOWING |
| `engine.py` warnings | warnings list | coverage_by_function from computed coverage stats | Yes — derived from actual solve metrics (req/served hours) | FLOWING |

---

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| All 80 tests pass (includes real CP-SAT engine tests, API integration tests, degeneracy detection, TEST-03 suite) | `uv run pytest -q` from backend/ | 80 passed, 1 warning in 5.72s | PASS |
| test_no_regression_empty_overrides (real CP-SAT, behavior-dependent) | run as part of suite | passes in 5.72s overall | PASS |
| test_scale_demand_honored (real CP-SAT, behavior-dependent) | run as part of suite | passes (factor=8.0 forces 2 members vs baseline 1) | PASS |
| test_exclude_worker_from_task_honored (real CP-SAT, behavior-dependent) | run as part of suite | passes (M0 off Pick, M1 alone covers demand) | PASS |
| test_set_max_hours_honored (real CP-SAT, behavior-dependent) | run as part of suite | passes (M0 capped forces solver to M1) | PASS |

---

### Prohibition Check

All plan-level prohibitions verified via code inspection:

| Prohibition | Verification | Status |
|-------------|-------------|--------|
| No per-call validation failure raises out of parse_and_store as a 400 | Router only catches LookupError; ValueError not raised by service | VERIFIED |
| No rejected or clarification entry persisted to scenario.overrides | Lines 368-373: only `if applied:` block writes to DB | VERIFIED |
| No override penalty term added to round1_unmet or as a hard constraint | All penalty terms in round2_cost only (builder.py lines 406-413) | VERIFIED |
| scale_demand does not mutate self.p.demand | Scale dict built separately; b.amount*f computed inline, p.demand never modified | VERIFIED |
| set_max_hours overflow var bounded by (hard_cap - max_hours)*VOL_SCALE | builder.py line 399: `max(0, hard_cap_scaled - scaled_max)` | VERIFIED |
| No out-of-bounds arg reaches the builder | Service validates factor>0, max_hours>0, day in range before appending to applied | VERIFIED |
| Degeneracy detection does not alter solver_status | engine.py: status from lex.status before detection loop; loop only appends to warnings list | VERIFIED |
| domain/result.py imports nothing from solver/web/llm layers | File imports only: dataclasses, typing | VERIFIED |
| No live LLM API called in TEST-03 tests | app.dependency_overrides[get_llm_provider] = lambda: StubLLMProvider() in client fixture | VERIFIED |

---

### Requirements Coverage

| Requirement ID | Description | Plan | Status | Evidence |
|---------------|-------------|------|--------|---------|
| NLC-02 | Text parsed into zero or more solver tool calls from fixed set of five | 02-01, 02-02 | SATISFIED | All five tools regex-matched in stub; all five elif branches in service; 80 tests pass |
| NLC-03 | No-tool text returns "no constraint found" | 02-01 | SATISFIED | no_constraint_found logic in service; test_no_constraint_found_in_text_returns_200_with_flag passes |
| NLC-04 | Response echoes human-readable parsed_constraint summary | 02-01, 02-02 | SATISFIED | parsed_constraint field in AppliedConstraint; wording strings for all 5 tools in service |
| NLC-05 | Ambiguous/unparseable input returns clarification_needed with question | 02-01 | SATISFIED | _PARTIAL_WORKERS_RE sentinel; multi-match paths in _resolve_task/_resolve_member; two clarification tests pass |
| VAL-01 | Tool-call arguments validated for type and bounds before solver | 02-02 | SATISFIED | factor>0, max_hours>0, day in horizon enforced; 4 OOB rejection tests pass |
| VAL-02 | Member/task references validated against real scenario IDs; unknown rejected | 02-01, 02-02 | SATISFIED | _resolve_task/_resolve_member return _ResolveResult with error on zero-match; tests confirm token named in error |
| VAL-03 | Validation failures return plain-English error naming the offending ref/arg and available options | 02-01, 02-02, 02-04 | SATISFIED | Error strings include "Valid tasks:…" and "Valid members:…"; test_rejection_error_names_ref asserts both parts |
| ENG-05 | Re-solving with overrides yields honored schedule; degenerate solves detected and flagged | 02-03 | SATISFIED | warnings field on SolveResult; detection loop in engine.py; serialize_result passes through warnings |
| TEST-03 | Validation tests cover unknown IDs and out-of-bounds args | 02-04 | SATISFIED | 5 new TEST-03 test functions; 36 total in test_constraints_api.py; all pass |

No orphaned requirements found. All 9 Phase 2 requirements accounted for.

---

### Anti-Patterns Found

No blockers, warnings, or notable patterns found:
- No TBD/FIXME/XXX/TODO/HACK markers in any phase-modified files
- No stub/placeholder implementations (all service branches are substantive)
- No return-null or empty-return patterns in rendering paths
- No hardcoded empty data in applied/rejected/warnings fields
- One `return []` in builder._candidate_starts (L152) is a legitimate guard — window too short for template, not a stub

---

### Human Verification Required

None. All truths are mechanically verifiable (code exists, is wired, data flows, and tests exercise behavior including real CP-SAT engine honoring).

---

## Gaps Summary

No gaps. All 5 roadmap success criteria verified. All 21 plan-level must-have truths verified. All 9 requirement IDs satisfied. 80 tests pass against actual codebase including real CP-SAT engine honor tests.

---

_Verified: 2026-06-29_
_Verifier: Claude (gsd-verifier)_
