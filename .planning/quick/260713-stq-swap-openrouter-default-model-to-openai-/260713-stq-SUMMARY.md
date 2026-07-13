---
phase: 260713-stq
plan: 01
subsystem: llm
tags: [openrouter, llm-provider, settings, pytest, live-test]

# Dependency graph
requires:
  - phase: 260713-pn3
    provides: OpenRouterLLMProvider registration + openrouter_model Settings field, originally defaulted to meta-llama/llama-3.3-70b-instruct:free
provides:
  - "_OPENROUTER_DEFAULT_MODEL swapped from meta-llama/llama-3.3-70b-instruct:free (upstream 429) to openai/gpt-oss-20b:free (live-verified tool-capable)"
affects: [llm-provider-config, openrouter-live-tests]

# Tech tracking
tech-stack:
  added: []
  patterns: []

key-files:
  created: []
  modified: [backend/settings.py]

key-decisions:
  - "Swapped only the _OPENROUTER_DEFAULT_MODEL constant + a one-line comment; left Settings.openrouter_model wiring, default_settings() OPENROUTER_MODEL env fallback, and the LLM_PROVIDER stub default untouched, per plan scope"
  - "Did NOT attempt to fix the newly-surfaced grounding-guard live test failure (day-index labels '0'/'1' emitted as literal numbers by the model, not admitted by _allowed_values) — plan explicitly directs reporting + stopping rather than silently working around an unrelated bug"

patterns-established: []

requirements-completed: [OPENROUTER-PROVIDER]

coverage:
  - id: D1
    description: "_OPENROUTER_DEFAULT_MODEL constant swapped to openai/gpt-oss-20b:free with explanatory comment; no other settings.py wiring touched"
    requirement: "OPENROUTER-PROVIDER"
    verification:
      - kind: unit
        ref: "grep -c 'openai/gpt-oss-20b:free' backend/settings.py"
        status: pass
  - id: D2
    description: "Full non-live pytest suite stays green after the constant swap (regression gate)"
    requirement: "OPENROUTER-PROVIDER"
    verification:
      - kind: unit
        ref: "cd backend && uv run pytest -q"
        status: pass
  - id: D3
    description: "Both @pytest.mark.live OpenRouter tests pass against the user's real OPENROUTER_API_KEY using the new default model"
    requirement: "OPENROUTER-PROVIDER"
    verification:
      - kind: integration
        ref: "tests/test_openrouter_provider.py::test_openrouter_parse_constraints_matches_stub_parity"
        status: pass
      - kind: integration
        ref: "tests/test_openrouter_provider.py::test_openrouter_generate_insights_passes_grounding_guard"
        status: fail
    human_judgment: true
    rationale: "The 429 rate-limit failure this plan targeted is resolved (key loaded correctly, both tests actually executed rather than skipping). One live test still fails, but for a reason unrelated to model choice: the model writes literal day-index labels ('Day 0:', 'Day 1:') in its prose, and _grounding_guard's _allowed_values() never admits the coverage_by_day dict KEYS (only their percentage VALUES), so the literal token '0' is rejected as ungrounded. This is a pre-existing gap in the grounding-guard/test design (added earlier the same day in quick task 260713-o5e) that could not previously surface because the live test always failed on the upstream 429 before reaching the guard. Per this plan's explicit Task 2 instruction, this is reported rather than silently fixed since it is outside this plan's declared scope (settings.py constant only) — needs a human decision on whether to widen _allowed_values to admit day-index integers, or constrain the insight prompt to avoid emitting raw day-index numbers."

# Metrics
duration: 12min
completed: 2026-07-13
status: complete
---

# Phase 260713-stq: Swap OpenRouter Default Model to openai/gpt-oss-20b:free Summary

**Swapped `_OPENROUTER_DEFAULT_MODEL` from the 429-throttled `meta-llama/llama-3.3-70b-instruct:free` to the live-verified `openai/gpt-oss-20b:free`, resolving the rate-limit failure but surfacing an unrelated, pre-existing grounding-guard gap in one live test.**

## Performance

- **Duration:** 12 min
- **Started:** 2026-07-13T13:52:00Z
- **Completed:** 2026-07-13T14:04:00Z
- **Tasks:** 2 completed
- **Files modified:** 1 (backend/settings.py)

## Accomplishments
- `_OPENROUTER_DEFAULT_MODEL` now `"openai/gpt-oss-20b:free"` with a one-line comment explaining the swap and dating the live verification (2026-07-13)
- Confirmed via grep that no other file in `backend/` still references the old `meta-llama/llama-3.3-70b-instruct:free` slug
- Full non-live pytest suite verified green (123 passed, 6 deselected, 0 failures) — the keyless-CI stub default and `default_settings()` wiring are unaffected
- Confirmed `OPENROUTER_API_KEY` loads correctly from `backend/.env` — both live-gated tests actually ran (no more skip), proving the 429 upstream-availability problem this plan targeted is resolved
- One of the two live tests (`test_openrouter_parse_constraints_matches_stub_parity`) now passes cleanly against the real API with the new model
- The other live test (`test_openrouter_generate_insights_passes_grounding_guard`) fails for a reason unrelated to model choice — full root cause captured below, not silently patched, per plan's explicit instruction

## Task Commits

Each task was committed atomically:

1. **Task 1: Swap the OpenRouter default model constant to openai/gpt-oss-20b:free** - `77134de` (fix)
2. **Task 2: Run non-live suite + live OpenRouter tests and record results in SUMMARY** - no code commit (verification + this SUMMARY.md only, per plan `files_modified`)

**Plan metadata:** commit deferred to orchestrator (per dispatch instructions, docs artifacts are not committed by the executor)

## Files Created/Modified
- `backend/settings.py` - `_OPENROUTER_DEFAULT_MODEL` constant changed from `"meta-llama/llama-3.3-70b-instruct:free"` to `"openai/gpt-oss-20b:free"`, plus a one-line explanatory comment above it. No other lines touched.

## Decisions Made
- Kept the change strictly scoped to the single constant + comment, exactly as directed — `Settings.openrouter_model` field wiring, the `default_settings()` `OPENROUTER_MODEL` env fallback, and the `LLM_PROVIDER` `"stub"` default are byte-identical to before.
- Did not attempt to fix the grounding-guard test failure discovered in Task 2 (see Issues Encountered) — the plan explicitly instructs reporting + stopping for failures unrelated to the model swap, and fixing `_grounding_guard`/`_allowed_values` or the insight prompt would be an architectural/behavioral change to `services/insight_service.py`, outside this plan's `files_modified: [backend/settings.py]` scope (Rule 4 territory — needs a human decision, not an auto-fix).

## Deviations from Plan

None in the code change itself — `backend/settings.py` was modified exactly as specified (single constant + one-line comment, nothing else touched).

**Verification deviation from plan's stated success criterion:** the plan's `<verification>` block declares `2 passed` as the exit condition for the live-test command; actual result was `1 failed, 1 passed`. This is not an auto-fixed deviation — per Task 2's explicit instruction ("If a live test still fails for a reason unrelated to the model choice... do NOT silently work around it: report the exact failing assertion and traceback in the SUMMARY and stop"), the failure is reported below rather than patched.

## Issues Encountered

**`test_openrouter_generate_insights_passes_grounding_guard` FAILED — genuine grounding-guard mismatch, unrelated to the model swap.**

Command: `cd backend && uv run pytest tests/test_openrouter_provider.py -m live -q -v`

Result: `1 failed, 1 passed, 15 deselected in 14.01s`

Failing assertion and traceback:
```
tests\test_openrouter_provider.py:384: in test_openrouter_generate_insights_passes_grounding_guard
    _grounding_guard(report, metrics)
services\insight_service.py:94: in _grounding_guard
    raise InsightGenerationError(
        f"Ungrounded number {tok!r} not found in run metrics (D-06)"
    )
E   services.insight_service.InsightGenerationError: Ungrounded number '0' not found in run metrics (D-06)
```

Root cause (confirmed by capturing the full live report text): the model renders the `coverage_by_day` breakdown with literal 0-based day-index labels, e.g.:

```
**Coverage by day**
- Day 0: 61.22 % (0.6122)
- Day 1: 95 % (0.95)
```

`services/insight_service.py:_allowed_values()` (lines 40-80) admits each `coverage_by_day` dict **value** (the percentage, via `admit_pct`) but never admits the dict **keys** (`"0"`, `"1"`, the day-index labels themselves). `_grounding_guard`'s regex (`_NUM_RE`) matches the literal `0` in "Day 0" as a numeric token, looks it up against the allowed-value set, finds nothing within `tol=0.05` of `0.0` (no run metric is near zero), and raises. Token `1` from "Day 1" happens to pass only because `1.0` is coincidentally an allowed value (the `Pick` function's `pct: 1.0`/100% coverage) — a false negative, not evidence the guard is correctly grounding day labels.

This is a **pre-existing test-design gap**, not something introduced by this plan's constant swap:
- The live test itself (`test_openrouter_generate_insights_passes_grounding_guard`) was added earlier the same day in quick task `260713-o5e` (commit `1623dae`).
- It could never previously execute past the API call because the old default model (`meta-llama/llama-3.3-70b-instruct:free`) was returning upstream 429s — so this grounding-guard gap has never actually been exercised against a real completion until this verification run.
- The gap is in `_allowed_values()` / the insight prompt (`services/insight_service.py`), not in `backend/settings.py` — outside this plan's declared `files_modified` scope.

**Not fixed, per plan's explicit Task 2 instruction.** This needs a follow-up decision (architectural — Rule 4 territory): either widen `_allowed_values()` to admit `coverage_by_day` dict keys as literal day-index integers, or adjust the insight-generation prompt to avoid citing raw day indices as bare numbers. Flagging for the user/next planning pass.

## User Setup Required

None - no external service configuration required. `OPENROUTER_API_KEY` was already present in `backend/.env` per the plan's `user_setup` note, and loaded correctly (confirmed by both live tests actually running rather than skipping).

## Next Phase Readiness

- The upstream 429 rate-limit issue this plan targeted is resolved — `openai/gpt-oss-20b:free` is live-verified as answering both a plain completion and a tool-calling request.
- Non-live suite remains fully green (123 passed, 6 deselected, 0 failures) — no regression from the constant swap.
- **Open item:** the `_grounding_guard`/`_allowed_values` day-index gap in `services/insight_service.py` blocks a fully clean live-test run for the OpenRouter provider. Recommend a small follow-up quick task or plan to either extend `_allowed_values()` to admit `coverage_by_day` keys, or adjust the insight prompt template to avoid citing bare day-index numbers.

---
*Phase: 260713-stq*
*Completed: 2026-07-13*

## Self-Check: PASSED

- FOUND: backend/settings.py (grep confirms `openai/gpt-oss-20b:free` present, count=1)
- FOUND: commit 77134de in git log
