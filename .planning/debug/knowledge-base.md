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

