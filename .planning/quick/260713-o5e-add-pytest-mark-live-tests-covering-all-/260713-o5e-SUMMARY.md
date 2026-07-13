---
task: 260713-o5e
title: Add @pytest.mark.live tests covering all LLMProvider operations
status: complete
tags: [gemini, llm, testing, grounding-guard, live-tests]
key-files:
  created: []
  modified:
    - backend/tests/test_gemini_provider.py
commits:
  - 00763bb
  - 5e69664
---

# 260713-o5e: Add @pytest.mark.live tests covering all LLMProvider operations Summary

Closes the test-coverage gap identified while debugging `insight-api-502-ungrounded`:
the only existing live-gated test (`test_gemini_parse_constraints_matches_stub_parity`)
covered `parse_constraints` but never `generate_insights`, so the real Gemini provider's
output had never been run through the D-06 grounding guard before the bug surfaced in
manual testing. Both new tests follow the existing pattern — `@pytest.mark.live` +
`@pytest.mark.skipif(not _HAS_KEY, ...)` — so they stay excluded from the default
`-m "not live"` suite (D-09/TEST-01) and only run locally when a developer has a real
`GEMINI_API_KEY`.

## What Changed

### Task 1 — `test_gemini_generate_insights_passes_grounding_guard`

- Builds a metrics dict shaped after the real run (`418577f3`) that triggered the
  original bug: Putaways coverage `pct=0.9814814814814815` (98.148%), plus
  `total_unmet_hours`, `total_cost`, and day-0 coverage values requiring whole-number
  rounding.
- Calls the real `GeminiProvider.generate_insights`, then runs the result through the
  **real** `services.insight_service._grounding_guard` (imported directly, not a copy)
  and asserts it does not raise.
- Asserts a non-empty report so an empty/safety-blocked Gemini response can't
  vacuously pass the guard.
- This is the automated regression net for `insight-api-502-ungrounded` — previously
  that fix was only confirmed by one manual human-verification call.

### Task 2 — `test_gemini_parse_constraints_more_phrasings_match_stub`

- Parametrized over two additional tool phrasings beyond the sole pre-existing
  "at least 2 on Pick" case: `scale_demand` ("scale Pick demand by 2x" → factor 2.0)
  and `set_max_hours` ("cap Alice at 40 hours" → max_hours 40.0).
- Compares Gemini's parsed `OverrideCall` against the stub's for tool name and
  coerced numeric arg only — task_id/member_id token casing is intentionally not
  asserted (D-06 reframed parity: `constraint_service`'s substring resolver,
  VAL-02, absorbs LLM phrasing variance either way).

## Verification

- `cd backend && uv run python -m pytest -m "not live" -q` → `108 passed, 4 deselected`
  — both new live tests correctly excluded from the default suite.
- `cd backend && uv run python -m pytest tests/test_gemini_provider.py -m live --collect-only -q`
  → `4/15 tests collected` (1 pre-existing + 2 new, one parametrized into 2 cases),
  no import/collection errors.
- No live API calls were made during verification (no `GEMINI_API_KEY` assumed
  available in this environment) — collection-only proof was sufficient per task
  constraints.

## Deviations from Plan

None.

## Issues Encountered

None during execution. (Note: the orchestrator's post-execution worktree cleanup
initially deleted this SUMMARY.md file due to `.planning/` being a shared path
between the worktree and the main checkout rather than a duplicated one; it was
reconstructed from the two commits' full messages and diff stats, which were
unaffected since they live in git history on the `worktree-agent-a0dca072d9ad66a37`
branch.)

## Self-Check: PASSED

- FOUND: backend/tests/test_gemini_provider.py (both new tests present)
- FOUND commit 00763bb (test(260713-o5e): live regression test for generate_insights vs real grounding guard)
- FOUND commit 5e69664 (test(260713-o5e): broaden live parse_constraints parity to scale_demand/set_max_hours)
