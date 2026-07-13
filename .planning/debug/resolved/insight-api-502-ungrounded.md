---
status: resolved
trigger: "I run the get insight API and get error 502 Bad Gateway, how can I/we trace the issue?"
created: 2026-07-13T09:45:16Z
updated: 2026-07-13T10:25:00Z
---

## Current Focus
<!-- OVERWRITE on each update - always reflects NOW -->

reasoning_checkpoint:
  hypothesis: "The D-06 grounding guard (_allowed_values in insight_service.py) omits integer rounding from its allowed-value ladder. It admits raw metric values, round(x,1), round(x,2), and for coverage pct*100 + round(pct*100,1) — but never round(x,0). LLMs express metrics as whole numbers in prose ('98%', '212 hours'), so faithful whole-number roundings of real metrics fail the guard and surface as HTTP 502."
  confirming_evidence:
    - "Real run 418577f3 metric Putaways pct=0.9814814814814815 -> *100 = 98.148%. Guard admits 98.148 and round(98.148,1)=98.1 but not round(98.148,0)=98."
    - "Deterministic repro against the live DB metrics: _grounding_guard('98', metrics) raises the EXACT reported error 'Ungrounded number 98 not found in run metrics (D-06)'."
    - "Same class confirmed for other metrics: '212' (unmet 212.127), '11,550' (cost 11549.71), '61%' (day-0 0.6122) all rejected; '212.13', '10', '40' pass. Only whole-number rounding is missing."
  falsification_test: "After adding round(x,0) to the admit ladder and integer rounding to both coverage percentage handlers, _grounding_guard('98'/'212'/'11550'/'61%', metrics) must NOT raise, while a genuine fabrication ('99999') must STILL raise."
  fix_rationale: "The guard already accepts 1- and 2-decimal rounding, acknowledging the LLM rounds. Integer rounding is the missing rung of the same ladder. Adding round(x,0) admits exactly the nearest whole number of each real metric (a faithful representation), not an arbitrary range — a fabricated 99999 is still nowhere near any metric's integer rounding, so the anti-fabrication property (D-06) is preserved."
  blind_spots: "The real Gemini report may contain OTHER ungrounded tokens beyond rounding — e.g. structural counts like '7 days' or the model recomputing a derived figure — which this fix does not address. Those are inherent to string-level grounding and cannot be reproduced without a live API key. Human verification against the live endpoint is still required."

next_action: Edit backend/services/insight_service.py _allowed_values to add round(x,0) to admit() and integer rounding to both coverage percentage handlers; then re-run the deterministic guard experiment + full test suite.

## Symptoms
<!-- Written during gathering, then immutable -->

expected: Calling the get-insight API for a completed run should return a plain-language insight report derived from that run's metrics.
actual: Request returns HTTP 502 after ~4 seconds, with JSON body `{"detail": "Ungrounded number '98' not found in run metrics (D-06)"}`.
errors: HTTP 502 Bad Gateway; detail: "Ungrounded number '98' not found in run metrics (D-06)"
reproduction: Call the insight endpoint via Swagger UI at http://127.0.0.1:8123/docs (local uvicorn dev server, no reverse proxy involved) using "Try it out" / Execute.
started: Never worked — first time trying this endpoint.

## Eliminated
<!-- APPEND only - prevents re-investigating after /clear -->

## Evidence
<!-- APPEND only - facts discovered during investigation -->

- timestamp: 2026-07-13T09:52:00Z
  checked: backend/api/routers/runs.py:88-91 and services/insight_service.py:75-88
  found: get_run_insights maps insight_service.InsightGenerationError -> HTTP 502. That error is raised by _grounding_guard when any numeric token in the LLM report is not within tol=0.05 of a value in _allowed_values(metrics). The 502 (D-08) is deliberate for "insight generation failed", not a proxy/gateway fault.
  implication: The 502 originates in the app itself (no reverse proxy involved, matching the symptom). Cause is the grounding guard rejecting '98'.

- timestamp: 2026-07-13T09:56:00Z
  checked: services/insight_service.py:40-72 (_allowed_values) rounding ladder
  found: admit() adds x, round(x,1), round(x,2) — no round(x,0). Coverage handlers add pct*100 and round(pct*100,1) for coverage_by_function, and only p*100 (no rounding) for coverage_by_day. Integer/whole-number rounding is admitted nowhere.
  implication: Any LLM report citing a metric as a whole number (the natural prose form) is rejected as ungrounded.

- timestamp: 2026-07-13T10:00:00Z
  checked: live DB backend/var/rosterai.db latest COMPLETED run 418577f3 metrics
  found: coverage_by_function.Putaways.pct = 0.9814814814814815 (=> 98.148%). Deterministic experiment: _grounding_guard('98', metrics) raises EXACTLY "Ungrounded number '98' not found in run metrics (D-06)". Same rejection for '212' (unmet 212.12665), '11,550' (cost 11549.71), '61%' (day-0 0.61216). '212.13', '10', '40' pass.
  implication: ROOT CAUSE confirmed. '98' is the Putaways coverage rounded to a whole percent by Gemini — a faithful rounding of a real metric, not a fabrication. The guard's missing integer-rounding rung is the defect.

## Resolution
<!-- OVERWRITE as understanding evolves -->

root_cause: The D-06 grounding guard's allowed-value ladder in insight_service._allowed_values omits whole-number rounding (round(x,0)). It admits raw metric values, round(x,1), round(x,2), and for coverage pct*100 + round(pct*100,1) — but never the integer form. LLM insight prose expresses metrics as whole numbers ("98%" for a 98.148% coverage, "212 hours", "11,550 cost"), so faithful roundings of real metrics fail the guard, and the router maps InsightGenerationError to HTTP 502. The reported '98' is the Putaways function's 98.148% coverage rounded to a whole percent.
fix: In backend/services/insight_service.py _allowed_values, added the whole-number rung round(x,0) to the admit() rounding ladder (previously only raw, round(.,1), round(.,2)), and introduced admit_pct(fraction) so both coverage_by_function and coverage_by_day admit the fraction AND its ×100 percentage form through the full ladder. This makes faithful whole-number roundings of real metrics ("98%", "212", "11,550", "61%") pass the guard while genuine fabrications (99999, 500) remain rejected — the D-06 anti-fabrication property is preserved.
verification: |
  - Deterministic guard experiment against the live DB metrics (run 418577f3): '98'/'98%'/'212'/'11,550'/'61%' now PASS; '99999'/'500' still REJECT. Falsification test satisfied.
  - Full backend suite via `uv run python -m pytest`: 107 passed, 1 deselected (was 107 passed pre-fix — no regressions).
  - Added regression test tests/test_insights_api.py::test_grounding_guard_accepts_whole_number_roundings (9 insights tests pass).
  - RESIDUAL (needs human check): a live Gemini report could still 502 on a non-metric token the guard cannot ground (e.g. structural counts like "7 days"). Not reproducible without a live API key.
  - HUMAN VERIFIED (2026-07-13): user re-ran GET /runs/{run_id}/insights against the live Gemini provider; returned the insight successfully with no 502 error. Confirmed fixed.
files_changed:
  - backend/services/insight_service.py (fix: integer-rounding rung + admit_pct helper)
  - backend/tests/test_insights_api.py (regression test)
