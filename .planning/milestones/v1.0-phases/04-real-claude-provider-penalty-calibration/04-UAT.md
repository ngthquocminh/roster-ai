---
status: complete
phase: 04-real-claude-provider-penalty-calibration
source: [04-01-SUMMARY.md, 04-02-SUMMARY.md, 04-03-SUMMARY.md]
started: 2026-07-13T15:26:18Z
updated: 2026-07-15T00:00:00Z
---

## Current Test
<!-- OVERWRITE each test - shows where we are -->

[testing complete]

## Tests

### 1. Switch to Real OpenRouter Provider (config only)
expected: |
  With `backend/` as your working directory, set environment variables
  `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY=<your real OpenRouter
  key>` (optionally `OPENROUTER_MODEL`, defaults to `openai/gpt-oss-20b:free`),
  then start the API server (e.g. `uv run uvicorn api.main:app`). The server
  starts cleanly with no errors — no service or router code needs to change
  to point it at the real provider.
result: pass

### 2. Parse a Live Constraint
expected: |
  With the server still running against the real OpenRouter provider, submit
  a plain-English constraint via `POST /scenarios/{id}/constraints` (e.g.
  "Don't schedule <worker> on Saturday") for an existing scenario. You get
  back a 200 response with a `parsed_constraint` echo of what was
  understood — structurally the same shape you'd get from the stub provider,
  just parsed by the live model this time.
result: pass

### 3. Re-solve Reflects the Live-Parsed Override
expected: |
  Trigger a re-solve on that scenario. The returned schedule visibly honors
  the constraint you just described in English (e.g., the named worker isn't
  scheduled on Saturday) — proving the full plain-English → live OpenRouter
  → validated override → re-solved schedule path works end to end.
result: pass

### 4. Shared to_override_call helper extracted; stub's five call sites route through it; private _to_override_call removed
expected: Shared to_override_call helper extracted; stub's five call sites route through it; private _to_override_call removed
result: pass
source: automated
coverage_id: D1

### 5. Settings carries llm_provider/llm_model/llm_api_key, env-driven, defaulting to stub/gemini-2.5-flash/None
expected: Settings carries llm_provider/llm_model/llm_api_key, env-driven, defaulting to stub/gemini-2.5-flash/None
result: pass
source: automated
coverage_id: D2

### 6. get_llm_provider is env-driven via settings.llm_provider; create_provider accepts a settings kwarg; no service/route code changed
expected: get_llm_provider is env-driven via settings.llm_provider; create_provider accepts a settings kwarg; no service/route code changed
result: pass
source: automated
coverage_id: D3

### 7. Full non-live suite stays green with no GEMINI_API_KEY set (keyless CI)
expected: Full non-live suite stays green with no GEMINI_API_KEY set (keyless CI)
result: pass
source: automated
coverage_id: D4

### 8. google-genai 2.10.0 installed and locked; create_provider('gemini', settings=...) returns a GeminiLLMProvider named 'gemini' without requiring a real API key
expected: google-genai 2.10.0 installed and locked; create_provider('gemini', settings=...) returns a GeminiLLMProvider named 'gemini' without requiring a real API key
result: pass
source: automated
coverage_id: D1

### 9. GeminiLLMProvider.parse_constraints translates the SDK's function_calls into list[OverrideCall] via the shared to_override_call helper (parity with the stub's translation path); empty/None function_calls yields []
expected: GeminiLLMProvider.parse_constraints translates the SDK's function_calls into list[OverrideCall] via the shared to_override_call helper (parity with the stub's translation path); empty/None function_calls yields []
result: pass
source: automated
coverage_id: D2

### 10. GeminiLLMProvider.generate_insights returns plain text generation output verbatim (no tools)
expected: GeminiLLMProvider.generate_insights returns plain text generation output verbatim (no tools)
result: pass
source: automated
coverage_id: D3

### 11. The 'live' pytest marker + addopts='-m "not live"' exclude the one live parity test from a bare pytest run by default, and it self-skips when GEMINI_API_KEY is absent
expected: The 'live' pytest marker + addopts='-m "not live"' exclude the one live parity test from a bare pytest run by default, and it self-skips when GEMINI_API_KEY is absent
result: pass
source: automated
coverage_id: D4

### 12. The Gemini API key never appears in any log, exception, or response string in backend/llm/gemini.py
expected: The Gemini API key never appears in any log, exception, or response string in backend/llm/gemini.py
result: pass
source: automated
coverage_id: D5

### 13. Four *_PENALTY constants in config/constants.py carry calibrated integer values (replacing the 100_000/50_000 placeholders) with derivation comments citing scripts/calibrate_penalties.py
expected: Four *_PENALTY constants in config/constants.py carry calibrated integer values (replacing the 100_000/50_000 placeholders) with derivation comments citing scripts/calibrate_penalties.py
result: pass
source: automated
coverage_id: D1

### 14. A satisfiable override (scale_demand) is visibly honored by the real CP-SAT engine — more distinct bodies assigned than the wage-only baseline, solve stays OPTIMAL/FEASIBLE
expected: A satisfiable override (scale_demand) is visibly honored by the real CP-SAT engine — more distinct bodies assigned than the wage-only baseline, solve stays OPTIMAL/FEASIBLE
result: pass
source: automated
coverage_id: D2

### 15. An unsatisfiable override (exclude_worker_from_task with no idle replacement) degrades gracefully — solve stays OPTIMAL/FEASIBLE and the round-2 cost delta is bounded to a small multiple of baseline, never dominating
expected: An unsatisfiable override (exclude_worker_from_task with no idle replacement) degrades gracefully — solve stays OPTIMAL/FEASIBLE and the round-2 cost delta is bounded to a small multiple of baseline, never dominating
result: pass
source: automated
coverage_id: D3

### 16. CpSatEngine.solve() itself produces a non-empty warnings list naming the starved function for a zero-supply demanded task (folded WR-05 / ENG-05)
expected: CpSatEngine.solve() itself produces a non-empty warnings list naming the starved function for a zero-supply demanded task (folded WR-05 / ENG-05)
result: pass
source: automated
coverage_id: D4

### 17. Provider Swap Is Reversible / Stays Keyless By Default
expected: |
  Unset `LLM_PROVIDER` (or set it back to `stub`) and restart the server with
  no `GEMINI_API_KEY` or `OPENROUTER_API_KEY` present — it starts cleanly and
  behaves as before, and the project's default test suite
  (`uv run pytest -q -k "not live"`) still passes with zero network calls and
  no API key required.
result: pass

## Summary

total: 17
passed: 17
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none yet]
