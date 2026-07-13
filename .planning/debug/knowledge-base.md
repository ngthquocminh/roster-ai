# GSD Debug Knowledge Base

Resolved debug sessions. Used by `gsd-debugger` to surface known-pattern hypotheses at the start of new investigations.

---

## insight-api-502-ungrounded — D-06 grounding guard rejects whole-number roundings of real metrics as 502
- **Date:** 2026-07-13
- **Error patterns:** 502, Bad Gateway, Ungrounded number, not found in run metrics, D-06, grounding guard, InsightGenerationError, coverage percentage, rounding
- **Root cause:** `_allowed_values` in `backend/services/insight_service.py` only admitted raw metric values plus `round(x,1)`/`round(x,2)` variants, never `round(x,0)`. LLM insight prose naturally cites metrics as whole numbers (e.g. "98%" for a 98.148% coverage), so faithful roundings of real metrics were rejected as ungrounded, and the router mapped `InsightGenerationError` to HTTP 502.
- **Fix:** Added the `round(x,0)` rung to the `admit()` rounding ladder and an `admit_pct(fraction)` helper so both `coverage_by_function` and `coverage_by_day` admit the fraction and its ×100 percentage form through the full rounding ladder (0/1/2 decimal places). Fabricated numbers remain rejected — the D-06 anti-fabrication property is preserved.
- **Files changed:** backend/services/insight_service.py, backend/tests/test_insights_api.py
---

## ungrounded-number-0-not-found — D-06 grounding guard rejects 0-based day-index labels cited in prose as 502
- **Date:** 2026-07-13
- **Error patterns:** Ungrounded number '0', not found in run metrics, D-06, grounding guard, InsightGenerationError, 502, coverage_by_day, day index, day label
- **Root cause:** `_allowed_values` in `backend/services/insight_service.py` iterated `coverage_by_day` with `.values()` only, admitting each day's coverage percentage but never the dict KEYS — the 0-based day-index labels ("0".."6", serialized via serialize.py as `{str(d): pct}`). The insight prompt hands the LLM the raw summary (which contains `coverage_by_day={"0":0.61,...}`) and tells it to cite exact figures, so a faithful per-day line like "Day 0: 61%" cites the real key "0". The guard tokenized the bare "0", found no matching allowed value (unless a metric coincidentally rounded to 0), and raised "Ungrounded number '0' not found in run metrics (D-06)", mapped to HTTP 502. Distinct gap from insight-api-502-ungrounded (that fix handled metric VALUES; this is the structural dict-KEY-as-label class it flagged as residual).
- **Fix:** Changed the `coverage_by_day` loop from `.values()` to `.items()` and admit each numeric day-index KEY (coerced via `float(d)`, non-numeric keys skipped) alongside its percentage. Admits only the actual day indices of this run (bounded, known set), so faithful labels like "Day 0" pass while fabricated indices ("Day 42") and fabricated metrics (99999) are still rejected — D-06 anti-fabrication preserved. Verified deterministically (repro + falsification) and via full suite (124 passed); live-provider re-run skipped per user decision.
- **Files changed:** backend/services/insight_service.py, backend/tests/test_insights_api.py
---

