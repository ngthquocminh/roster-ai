---
phase: 03-on-demand-insight-reports
verified: 2026-06-30T00:00:00Z
status: passed
score: 8/8 must-haves verified
behavior_unverified: 0
overrides_applied: 0
---

# Phase 03: On-Demand Insight Reports Verification Report

**Phase Goal:** A user can fetch a natural-language insight report for a completed run that cites the run's real metric values, generated as a separate on-demand step that can never invalidate a successfully computed schedule.
**Verified:** 2026-06-30
**Status:** passed
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | GET /runs/{run_id}/insights on a COMPLETED run returns 200 with ready=true and a non-empty report that cites the run's metric values (D-01, INS-01) | VERIFIED | test_insights_returns_report_for_completed_run passes; asserts status 200, ready=True, "123" and "2" in report |
| 2 | GET on a run that is not COMPLETED returns 200 with ready=false plus the current status and a reason — NOT 409 (D-07) | VERIFIED | test_insights_not_ready_returns_200_body passes; asserts HTTP 200 always, ready=False path checked for status field |
| 3 | A second GET on the same run returns the cached runs.insight_json without re-calling the provider (INS-04) | VERIFIED | test_second_fetch_uses_cache passes with CountingInsightProvider; asserts identical bodies and call_count == 1 |
| 4 | Every number printed in the report matches a value derived from the run's metrics dict; the report is generated and grounded BEFORE anything is cached (D-06, INS-03) | VERIFIED | _grounding_guard called before set_insight in insight_service.py line 147; test_grounding_guard_rejects_fabricated_number proves 99999 -> 502 and nothing cached |
| 5 | Forcing the provider to fail leaves the run status COMPLETED and result_json untouched; only the insight call returns 502 and nothing is cached (D-08, INS-02) | VERIFIED | test_provider_failure_leaves_run_completed passes; asserts 502, run status COMPLETED, result_json unchanged, recovery GET returns 200 |
| 6 | A report containing a number absent from the run's metrics is rejected by the D-06 guard -> 502, nothing cached (D-06, INS-03) | VERIFIED | test_grounding_guard_rejects_fabricated_number passes; FabricatingInsightProvider returns 99999, rejected with 502, recovery generates successfully |
| 7 | A run carrying a degenerate-family warning has that warning narrated honestly in the report rather than reported as success (D-05 item 3, INS-03) | VERIFIED | test_report_narrates_degenerate_warnings passes; DegenerateStubEngine warning text appears verbatim in report with "WARNING" prefix |
| 8 | StubLLMProvider.generate_insights is deterministic and performs no I/O (LLM-01, TEST-01) | VERIFIED | test_generate_insights_deterministic passes; two calls with identical summary return identical text; "450" and "3.5" present in output |

**Score:** 8/8 truths verified

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `backend/services/insight_service.py` | get_or_generate, InsightGenerationError, _grounding_guard, _allowed_values | VERIFIED | All four symbols present; file is substantive (152 lines); imported and called from runs.py |
| `GET /runs/{run_id}/insights` route in `backend/api/routers/runs.py` | sync def (not async) | VERIFIED | `def get_run_insights` at line 70; confirmed not async; Depends(get_llm_provider) wired |
| `runs.insight_json TEXT` column in `backend/store/db.py` | DDL column + idempotent ALTER guard in init_db | VERIFIED | Column at line 29 of DDL; _has_column guard at lines 57-58; ALTER TABLE only if absent |
| `RunRepo.set_insight` in `backend/store/repositories.py` | Writes only insight_json via parameterized query | VERIFIED | Line 86; UPDATE runs SET insight_json=? WHERE id=?; no f-string; never touches status/result_json |
| `LLMProvider.generate_insights` Protocol op in `backend/llm/base.py` | Protocol method declaration | VERIFIED | Line 17: `def generate_insights(self, summary: dict) -> str: ...` |
| `StubLLMProvider.generate_insights` in `backend/llm/stub.py` | Deterministic, no I/O, covers D-05 topics | VERIFIED | Line 236-262; emits metric-grounded values only; all D-05 topics covered (coverage, cost/unmet, warnings, overrides) |
| `InsightOut` schema in `backend/api/schemas.py` | Pydantic model with ready, run_id, optional report/status/reason | VERIFIED | Line 34-39; ready:bool, run_id:str, Optional report/status/reason with None defaults |
| `backend/tests/test_insights_api.py` | 7 test functions + 3 test doubles | VERIFIED | 7 tests (3 happy + 4 negative); FailingInsightProvider, FabricatingInsightProvider, CountingInsightProvider present |
| `backend/tests/test_llm_provider.py` | test_generate_insights_deterministic appended | VERIFIED | Function at line 127; asserts determinism + cost/unmet values present in output |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| `backend/api/routers/runs.py` | `backend/api/deps.get_llm_provider` | `Depends(get_llm_provider)` at line 73 | WIRED | provider: LLMProvider = Depends(get_llm_provider); test client overrides this seam with lambda: StubLLMProvider() |
| `backend/services/insight_service.py` | `backend/store/repositories.RunRepo.set_insight` | called after _grounding_guard in get_or_generate line 149 | WIRED | Guard runs at line 147, set_insight at line 149 — fabricated numbers never persisted |
| `backend/services/insight_service.py` | `backend/services/serialize.py` metric shape | same metrics dict used for summary and allowed-value set | WIRED | result = json.loads(run["result_json"]); metrics = result["metrics"] — same dict passed to both provider.generate_insights and _grounding_guard |
| `backend/api/routers/runs.py` | `backend/services/insight_service.InsightGenerationError` | except clause at line 90 -> 502 | WIRED | LookupError -> 404; InsightGenerationError -> 502 |
| `backend/tests/test_insights_api.py` | `backend/api.deps.get_llm_provider` | app.dependency_overrides[get_llm_provider] in each negative test | WIRED | All three negative-path tests install failure/fabricating/counting providers per-test and clear overrides after |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|-------------------|--------|
| `GET /runs/{run_id}/insights` | run["result_json"]["metrics"] | RunRepo.get -> json.loads -> serialize_result output stored in DB | Yes — serialize_result writes total_cost, total_unmet_hours, coverage_by_function (with pct=served_h/required_h), coverage_by_day | FLOWING |
| `_grounding_guard` | allowed values set | _allowed_values(metrics) from same result["metrics"] dict | Yes — derived from real metric values; pct*100 conversion for fraction->percentage (Pitfall 3) | FLOWING |
| `StubLLMProvider.generate_insights` | cost_s, unmet_s, coverage lines | summary["metrics"] passed from get_or_generate | Yes — all numeric tokens read from summary["metrics"]; no hardcoded values | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Full insight test suite (7 tests) | `uv run python -m pytest tests/test_insights_api.py -v` | 7 passed, 1 warning in 1.67s | PASS |
| LLM provider test suite (13 tests) | `uv run python -m pytest tests/test_llm_provider.py -v` | 13 passed in 0.38s | PASS |
| Full workspace suite | `uv run python -m pytest -q` | 88 passed, 1 warning in 7.14s | PASS |
| Route is sync def (not async) | `grep "async def get_run_insights" backend/api/routers/runs.py` | no output | PASS |
| insight_json in DDL + ALTER guard | `grep "insight_json" backend/store/db.py` | lines 29, 57, 58 | PASS |
| set_insight uses ? placeholders | source review of repositories.py line 88 | UPDATE runs SET insight_json=? WHERE id=? | PASS |
| grounding guard before set_insight | source review of insight_service.py lines 147-149 | _grounding_guard called at line 147; set_insight at line 149 | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| INS-01 | 03-01 | An endpoint generates a natural-language insight report from a completed run's metrics | SATISFIED | GET /runs/{run_id}/insights exists; test_insights_returns_report_for_completed_run asserts 200 + ready=true + non-empty grounded report |
| INS-02 | 03-02 | Insights are generated as a separate, on-demand step; an LLM failure never changes run status or invalidates the schedule result | SATISFIED | test_provider_failure_leaves_run_completed asserts 502 + run status COMPLETED + result_json unchanged; set_insight only writes insight_json |
| INS-03 | 03-01, 03-02 | The insight report cites specific metric values from the run (no generic "coverage was adequate" language) | SATISFIED | _grounding_guard enforces numeric grounding; test_grounding_guard_rejects_fabricated_number proves 99999 rejected; test_report_narrates_degenerate_warnings proves warnings narrated verbatim |
| INS-04 | 03-01 | The insight result is cached (runs.insight_json) so repeat fetches don't re-call the LLM | SATISFIED | cache short-circuit at insight_service.py line 125-126; test_second_fetch_uses_cache with CountingInsightProvider asserts call_count == 1 |

**Orphaned requirements check:** REQUIREMENTS.md traceability maps exactly INS-01, INS-02, INS-03, INS-04 to Phase 3. Plans 03-01 and 03-02 together claim all four. No orphaned requirements.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| None | — | — | — | — |

No TBD, FIXME, XXX, TODO, HACK, or PLACEHOLDER markers found in any phase-modified file. No stub implementations, empty returns, or hardcoded empty data in production paths.

One note on `_has_column` in `store/db.py` (line 39): uses an f-string in `PRAGMA table_info({table})`. This is not a security risk because the only caller is `init_db` which passes the literal string "runs" — no user input reaches this path.

### Human Verification Required

None. All must-haves are verified by passing tests. No items requiring human judgment.

### Gaps Summary

No gaps. All 8 truths from the two plan must_haves sections are verified by passing behavioral tests. The full test suite is 88 passed. The phase goal is achieved: a user can call GET /runs/{run_id}/insights to receive a natural-language report grounded in the run's actual metric values; the generation is on-demand and separate from the solve; a provider failure leaves run status and result_json untouched; repeat calls return the cached report without re-calling the provider.

---

_Verified: 2026-06-30_
_Verifier: Claude (gsd-verifier)_
