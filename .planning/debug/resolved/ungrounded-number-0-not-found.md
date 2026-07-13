---
status: resolved
trigger: "InsightGenerationError: Ungrounded number '0' not found in run metrics (D-06)"
created: 2026-07-13T00:00:00Z
updated: 2026-07-13T12:30:00Z
---

## Current Focus
<!-- OVERWRITE on each update - always reflects NOW -->

reasoning_checkpoint:
  hypothesis: "The D-06 grounding guard (_allowed_values in backend/services/insight_service.py) iterates `coverage_by_day` with `.values()` only (line 78-79), admitting each day's coverage PERCENTAGE through admit_pct(), but never admitting the dict KEYS — the day-index labels (serialized as string digits \"0\",\"1\",...,\"6\" per services/serialize.py:35). When the LLM report cites a day by index in prose (e.g. \"Day 0: 61.22%\"), the guard tokenizes both '0' and '61.22' from the text; '61.22' passes via admit_pct but the bare '0' has no matching entry in the allowed-value set (unless a real metric happens to round to 0), so it raises exactly 'Ungrounded number '0' not found in run metrics (D-06)'."
  confirming_evidence:
    - "backend/services/insight_service.py:78-79 — `for p in (metrics.get('coverage_by_day') or {}).values(): admit_pct(p)` — only iterates .values(), day-index keys never reach _allowed_values()."
    - "backend/services/serialize.py:35 — coverage_by_day serialized as {str(d): _num(p) for d, p in m.coverage_by_day.items()} — keys are day indices 0..6 as strings."
    - "Prior resolved session .planning/debug/resolved/insight-api-502-ungrounded.md fixed the missing integer-rounding rung for metric VALUES (round(x,0) + admit_pct) but did not address admitting the coverage_by_day KEYS — a distinct gap in the same guard."
    - "Documented in project state (.planning/STATE.md Blockers/Concerns, added 2026-07-13 via quick task 260713-stq): 'a model that writes \"Day 0: 61.22%\" gets the bare 0 rejected as ungrounded (D-06 false positive)' — surfaced by a live OpenRouter generate_insights test."
  falsification_test: "After admitting coverage_by_day day-index keys (as ints, e.g. 0,1,2...,6) into _allowed_values(), _grounding_guard() must NOT raise for a report containing 'Day 0: 61.22%' / 'Day 3: 95%' etc., while a fabricated day index far outside the real range (e.g. 'Day 42') or a fabricated metric value must STILL raise."
  blind_spots: "Need to confirm the actual index range used (0-based vs 1-based in prose) and whether prompt instructs the LLM on day-labeling convention, to avoid overly widening the admitted set. Also need to check no other dict-key-as-label pattern exists elsewhere in the guard (e.g. coverage_by_function keys are function names, not numeric, so likely unaffected)."

next_action: RESOLVED. Per user decision (2026-07-13), verification accepted on the basis of the deterministic repro/falsification + full suite (124 passed, 0 failures, regression test added); the live OpenRouter/Gemini re-run was intentionally SKIPPED per user. Fix committed, session archived to resolved/, knowledge-base entry appended.

## Symptoms
<!-- Written during gathering, then immutable -->

expected: Calling insight generation (GET /runs/{run_id}/insights or generate_insights) for a completed run returns a plain-language report grounded in that run's real metrics.
actual: Insight generation raises `InsightGenerationError: Ungrounded number '0' not found in run metrics (D-06)` and the request fails (mapped to HTTP 502 by the router), even though the report is citing a real per-day coverage figure, not a fabricated one.
errors: "InsightGenerationError: Ungrounded number '0' not found in run metrics (D-06)"
reproduction: Generate an insight report whose prose cites a day-index alongside its coverage percentage (e.g. "Day 0: 61.22%"); surfaced via the live `@pytest.mark.live` OpenRouter `generate_insights` test added in quick task 260713-o5e / observed again in 260713-stq.
started: Surfaced 2026-07-13 once a live LLM call (OpenRouter, gpt-oss-20b:free) actually reached the D-06 guard with a real completion citing day-index numbers; previously invisible because no prior live run exercised this guard path with day-level citations.

## Eliminated
<!-- APPEND only - prevents re-investigating after /clear -->

## Evidence
<!-- APPEND only - facts discovered during investigation -->

- timestamp: 2026-07-13T00:00:00Z
  checked: backend/services/insight_service.py:40-80 (_allowed_values)
  found: "coverage_by_function loop admits required_h, served_h, and pct (via admit_pct) per function. coverage_by_day loop only does `.values()` -> admit_pct(p) for the percentage; the day-index key is never passed to admit() anywhere."
  implication: "Bare day-index numbers appearing in report prose (0,1,2,...) have no path into the allowed-value set unless they coincidentally match a rounded metric value."

- timestamp: 2026-07-13T00:00:00Z
  checked: backend/services/serialize.py:35
  found: "coverage_by_day keys are stringified day indices: {str(d): _num(p) for d, p in m.coverage_by_day.items()}, sourced from domain/result.py's `coverage_by_day: Dict[int, float]`."
  implication: "Day indices are small integers (0-based, one per scheduled day) — safe to admit as a bounded, known set derived directly from real metrics (not an open-ended range), preserving the anti-fabrication property of D-06."

- timestamp: 2026-07-13T12:00:00Z
  checked: backend/llm/openrouter.py:149-159 (_INSIGHT_PROMPT_TEMPLATE, verbatim mirror of gemini.py) and the summary dict built in insight_service.get_or_generate:151
  found: "The LLM is passed the RAW summary dict (metrics incl. coverage_by_day={'0':0.6122,...}, warnings, overrides) and instructed to 'cite exact figures from the summary'. The 0-based day keys ('0'..'6', per lock_worker_shift tool desc '0=Monday') ARE figures present in the summary — so 'Day 0' is a faithful citation of a real key, but the guard admits only .values(), never the keys."
  implication: "Root-cause mechanism confirmed end-to-end: prompt instructs citing summary figures; day-index keys are summary figures; guard omits them. The bare index is legitimately grounded data the guard fails to admit."

- timestamp: 2026-07-13T12:00:00Z
  checked: Deterministic repro — _grounding_guard('Coverage by day: Day 0: 61.22%, Day 1: 95%, Day 2: 88%.', metrics) with metrics.total_unmet_hours=212.13 (i.e. no metric coincidentally rounds to 0)
  found: "Tokens extracted = ['0','61.22','1','95','2','88']. `Is 0 currently admitted? False`. Guard RAISED the EXACT reported error: `Ungrounded number '0' not found in run metrics (D-06)`. The percentages ('61.22','95') pass via admit_pct; the day-index labels ('0','1','2') are the ungrounded tokens."
  implication: "ROOT CAUSE reproduced deterministically. The bare '0' is the day-index label for the first day (0-based). Fix: admit coverage_by_day KEYS (as numbers) into _allowed_values(); the value/percentage handling is already correct."

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: |
  The D-06 grounding guard's _allowed_values() (backend/services/insight_service.py)
  iterated coverage_by_day with `.values()` only, admitting each day's coverage
  PERCENTAGE but never the dict KEYS — the 0-based day-index labels ("0".."6",
  serialized via serialize.py:35 as {str(d): pct}). The insight prompt hands the LLM
  the raw summary (which contains coverage_by_day={"0":0.61,...}) and instructs it to
  "cite exact figures from the summary". A faithful per-day line such as "Day 0: 61%"
  therefore cites the real key "0", but the guard tokenizes the bare "0" and finds no
  matching allowed value (unless a metric coincidentally rounds to 0, e.g. a
  fully-covered run with total_unmet_hours=0), so it raised
  "Ungrounded number '0' not found in run metrics (D-06)". This is a distinct gap from
  the earlier insight-api-502-ungrounded fix (which added the integer-rounding rung for
  metric VALUES); that session even flagged this structural-label class as a residual.
fix: |
  In backend/services/insight_service.py _allowed_values(), changed the coverage_by_day
  loop from iterating `.values()` to `.items()` and admitting each day-index KEY (coerced
  via float(d), non-numeric keys skipped) alongside its percentage. This admits exactly
  the actual day indices of THIS run — a bounded, known set derived from real metrics — so
  faithful labels like "Day 0" pass while a fabricated index ("Day 42") and fabricated
  metrics (99999) are still rejected. The D-06 anti-fabrication property is preserved.
verification: |
  - Deterministic REPRO (pre-fix): _grounding_guard("Coverage by day: Day 0: 61.22%,
    Day 1: 95%, Day 2: 88%.", metrics) with total_unmet_hours=212.13 raised the EXACT
    reported error "Ungrounded number '0' not found in run metrics (D-06)". Tokens were
    ['0','61.22','1','95','2','88']; percentages passed, day-index labels did not.
  - Post-fix falsification: "Day 0/1/2" citations and a bare "Day 0" now PASS; a
    fabricated "Day 42" still RAISES ('42' ungrounded) and a fabricated 99999 still
    RAISES. Falsification test satisfied — anti-fabrication intact.
  - Full backend suite via `uv run python -m pytest`: 124 passed, 6 deselected
    (@pytest.mark.live), 0 failures — no regressions.
  - Added regression test tests/test_insights_api.py::test_grounding_guard_accepts_day_index_labels
    (10 insights tests pass).
  - LIVE-PROVIDER CHECK SKIPPED (user decision, 2026-07-13): the optional re-run of
    GET /runs/{run_id}/insights against the live OpenRouter/Gemini provider was
    intentionally not performed. The user accepted verification on the deterministic
    repro + falsification + full-suite evidence above (124 passed, regression test
    added), since the root cause and fix are exercised deterministically and the live
    path adds no new code coverage. Marked verified/resolved on that basis.
files_changed:
  - backend/services/insight_service.py (fix: admit coverage_by_day day-index keys)
  - backend/tests/test_insights_api.py (regression test)
