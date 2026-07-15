---
phase: 03-on-demand-insight-reports
plan: 02
subsystem: insight-endpoint-hardening
tags: [insights, grounding-guard, failure-isolation, test-doubles, determinism]
requires: [03-01]
provides: [negative-path-test-matrix, test-doubles, determinism-unit-test]
affects: [backend/tests]
tech_stack:
  added: []
  patterns:
    - inline test-double classes (FailingInsightProvider, FabricatingInsightProvider, CountingInsightProvider) for seam-level negative-path testing
    - in-test app.dependency_overrides injection for per-test provider switching
    - DegenerateStubEngine inline class for degenerate-family warning scenario
key_files:
  created: []
  modified:
    - backend/tests/test_insights_api.py
    - backend/tests/test_llm_provider.py
decisions:
  - upgraded test_second_fetch_uses_cache to use CountingInsightProvider (call_count==1 is strictly more rigorous than body-equality alone)
  - test doubles defined inline in test file (not shared fixtures) per PATTERNS.md recommendation — they are narrow and test-specific
  - DegenerateStubEngine defined inside test function body to keep degenerate-warning test self-contained
  - FabricatingInsightProvider emits literal "99999" — unambiguously absent from StubEngine metrics (total_cost=123, unmet=2) so guard rejects without tolerance ambiguity
metrics:
  duration: 17 min
  completed: 2026-06-30
  tasks_completed: 2
  files_created: 0
  files_modified: 2
status: complete
---

# Phase 03 Plan 02: Insight Endpoint Hardening Summary

**One-liner:** Negative-path test matrix with FailingInsightProvider, FabricatingInsightProvider, CountingInsightProvider — proves provider failure isolates run state, D-06 grounding guard rejects fabricated numbers, degenerate warnings narrated honestly, and StubLLMProvider is deterministic.

## What Was Built

Two test files extended (zero production code changes — this plan is the validation slice):

- **`backend/tests/test_insights_api.py`** — module docstring updated; `test_second_fetch_uses_cache` upgraded to use `CountingInsightProvider`; three inline test doubles appended; four new negative-path and edge-case tests added:
  - `FailingInsightProvider` — raises `RuntimeError` in `generate_insights`
  - `FabricatingInsightProvider` — returns `"Total cost was 99999."` (ungrounded number)
  - `CountingInsightProvider` — instance-level `call_count` counter, emits grounded cost+unmet text
  - `test_provider_failure_leaves_run_completed` — 502 on failure, run stays COMPLETED, result_json intact, nothing cached, recovery GET yields 200 (D-08, INS-02)
  - `test_grounding_guard_rejects_fabricated_number` — 502 on ungrounded 99999, nothing cached, recovery GET yields 200 (D-06, INS-03)
  - `test_report_narrates_degenerate_warnings` — DegenerateStubEngine (zero coverage, warning text), GET → 200, "WARNING" + exact warning text in report (D-05 item 3, INS-03)
  - `test_unknown_and_failed_run` — unknown id → 404; FailingStubEngine causes FAILED run → 200 ready=false (D-07, INS-02)

- **`backend/tests/test_llm_provider.py`** — `test_generate_insights_deterministic` appended:
  - Builds a representative summary dict (total_cost=450.0, total_unmet_hours=3.5, two functions with pct fractions, coverage_by_day, warnings, overrides)
  - Calls `StubLLMProvider().generate_insights` twice; asserts non-empty str, identical text (determinism, TEST-01/LLM-01), "450" and "3.5" present in output

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Failure-isolation, fabrication-rejection, degenerate-warning, and edge test matrix | b88616d | backend/tests/test_insights_api.py |
| 2 | generate_insights determinism unit test (LLM-01 / TEST-01) | 9e78a96 | backend/tests/test_llm_provider.py |

## Verification Results

```
uv run --directory backend pytest tests/test_insights_api.py -x -v
7 passed, 1 warning in 1.68s

uv run --directory backend pytest tests/test_llm_provider.py -x -v
13 passed in 0.38s

uv run --directory backend pytest -q
88 passed, 1 warning in 8.30s
```

All three plan verification commands exit 0. No network calls; stub-driven throughout.

Acceptance criteria checks:
- `test_provider_failure_leaves_run_completed` — PASSED (502, run COMPLETED, result intact, recovery 200)
- `test_grounding_guard_rejects_fabricated_number` — PASSED (502 on 99999, recovery 200)
- `test_report_narrates_degenerate_warnings` — PASSED ("WARNING" + exact text in report)
- `test_unknown_and_failed_run` — PASSED (404 unknown; 200 ready=false for FAILED)
- `test_second_fetch_uses_cache` — PASSED (CountingInsightProvider, call_count == 1)
- `test_generate_insights_deterministic` — PASSED (identical outputs, "450"+"3.5" present)
- `grep -n "FailingInsightProvider\|FabricatingInsightProvider\|CountingInsightProvider" backend/tests/test_insights_api.py` — all three doubles found

## Deviations from Plan

### Auto-fixed Issues

None.

### Deliberate Adjustments

**1. [Upgrade] test_second_fetch_uses_cache replaced with CountingInsightProvider variant**
- **Reason:** Plan explicitly required the counting variant (behavior block: "test_second_fetch_uses_cache (counting variant)"). The 03-01 version only checked body equality; the new version also verifies `call_count == 1`, which is strictly more rigorous.
- **Files modified:** backend/tests/test_insights_api.py
- **Commit:** b88616d

## Known Stubs

None — this plan adds only tests. No production stubs created.

## Threat Surface Scan

No new security-relevant surface. This plan modifies only test files. No new endpoints, no new DB schema, no new file access patterns.

## Threat Mitigation Proof

| Threat ID | Disposition | Test Proof |
|-----------|-------------|------------|
| T-3-02 (D-06 grounding guard) | mitigated | `test_grounding_guard_rejects_fabricated_number` — guard rejects 99999, 502, nothing cached |
| T-3-03 (run status / result_json integrity, D-08) | mitigated | `test_provider_failure_leaves_run_completed` — status COMPLETED + result_json unchanged post-failure |
| T-3-05 (degenerate warning masking, INS-03) | mitigated | `test_report_narrates_degenerate_warnings` — warning text appears verbatim in report |

## Self-Check: PASSED

Files modified:
- backend/tests/test_insights_api.py — FOUND
- backend/tests/test_llm_provider.py — FOUND

Key commits:
- b88616d — feat(03-02) Task 1 — FOUND
- 9e78a96 — feat(03-02) Task 2 — FOUND
