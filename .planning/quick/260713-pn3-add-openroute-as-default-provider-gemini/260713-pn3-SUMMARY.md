---
phase: 260713-pn3
plan: 01
subsystem: llm
tags: [openrouter, openai-sdk, llm-provider, tool-calling, gemini-parity]

# Dependency graph
requires:
  - phase: 04-real-claude-provider-penalty-calibration
    provides: GeminiLLMProvider shape/contract (deferred client construction, LLMProviderError mapping, translate seam) this plan mirrors
provides:
  - "openrouter" as a third, fully-registered, selectable LLMProvider (stub | gemini | openrouter)
  - Settings.openrouter_api_key / openrouter_model fields, env-driven via OPENROUTER_API_KEY / OPENROUTER_MODEL
  - backend/llm/openrouter.py with parse_constraints (tool-calling) and generate_insights (plain completion)
  - backend/tests/test_openrouter_provider.py mirroring the Gemini provider test suite
affects: [llm, settings, api/deps, testing]

# Tech tracking
tech-stack:
  added: ["openai>=1.40 (official OpenAI Python SDK, OpenRouter is OpenAI-API-compatible)"]
  patterns:
    - "Deferred client construction (_get_client) for every network-backed LLMProvider — keeps create_provider(...) keyless (D-04)"
    - "Vendor tool-call JSON never crosses the LLMProvider seam — parsed to a plain (name, args) pair inside parse_constraints, then routed through llm.translate.normalize_args + to_override_call (D-02/D-06/D-07)"

key-files:
  created:
    - backend/llm/openrouter.py
    - backend/tests/test_openrouter_provider.py
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/settings.py
    - backend/llm/base.py
    - backend/conftest.py

key-decisions:
  - "Default OpenRouter model verified live via the OpenRouter API (GET /api/v1/models?supported_parameters=tools) at implementation time: meta-llama/llama-3.3-70b-instruct:free — confirmed present and tool-capable as of 2026-07-13"
  - "openrouter_model is a separate Settings field from llm_model (which defaults to Gemini's gemini-2.5-flash, not a valid OpenRouter slug)"
  - "openai.OpenAIError (the SDK's base error class) is the catch target in both parse_constraints and generate_insights, mapped to a static-message LLMProviderError — no vendor detail or the API key ever crosses the seam"

patterns-established:
  - "Third-provider mirror pattern: any future LLMProvider implementation should copy llm/openrouter.py's structure (deferred client, same five tool schemas translated to the vendor's shape, static-message error mapping, verbatim system instruction / insight prompt reuse)"

requirements-completed: [OPENROUTER-PROVIDER]

coverage:
  - id: D1
    description: "create_provider('openrouter', settings=default_settings()) returns a keyless provider named 'openrouter'; create_provider('openrouter') with no settings raises ValueError"
    requirement: "OPENROUTER-PROVIDER"
    verification:
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_create_provider_openrouter_returns_openrouter_llm_provider"
        status: pass
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_create_provider_openrouter_without_settings_raises_value_error"
        status: pass
    human_judgment: false
  - id: D2
    description: "parse_constraints translates OpenRouter tool calls into list[OverrideCall] via the shared translate seam, with D-06 numeric coercion parity and NLC-03 no-match behavior"
    requirement: "OPENROUTER-PROVIDER"
    verification:
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_parse_constraints_translates_one_tool_call"
        status: pass
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_parse_constraints_coerces_float_int_arg_for_stub_parity"
        status: pass
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_parse_constraints_none_tool_calls_returns_empty_list"
        status: pass
    human_judgment: false
  - id: D3
    description: "generate_insights returns completion text verbatim; degrades to '' on missing/empty completion"
    requirement: "OPENROUTER-PROVIDER"
    verification:
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_generate_insights_returns_fake_content"
        status: pass
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_generate_insights_none_content_returns_empty_string"
        status: pass
    human_judgment: false
  - id: D4
    description: "openai SDK errors are re-raised as the neutral llm.base.LLMProviderError — no vendor exception type crosses the seam"
    requirement: "OPENROUTER-PROVIDER"
    verification:
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_parse_constraints_maps_vendor_api_error_to_llm_provider_error"
        status: pass
      - kind: unit
        ref: "backend/tests/test_openrouter_provider.py#test_generate_insights_maps_vendor_api_error_to_llm_provider_error"
        status: pass
    human_judgment: false
  - id: D5
    description: "Keyless-default-CI invariant unchanged: default_settings().llm_provider is still 'stub' when LLM_PROVIDER is unset"
    verification:
      - kind: unit
        ref: "backend/tests/test_llm_provider.py#test_default_settings_llm_defaults_keyless"
        status: pass
    human_judgment: false
  - id: D6
    description: "Full non-live backend test suite passes after the change (no regressions to stub/gemini/api/engine tests)"
    verification:
      - kind: unit
        ref: "cd backend && python -m pytest -q (123 passed, 6 deselected)"
        status: pass
    human_judgment: false

duration: ~10min
completed: 2026-07-13
status: complete
---

# Quick Task 260713-pn3: Add OpenRouter as a Selectable LLM Provider Summary

**Added `OpenRouterLLMProvider` (OpenAI-SDK-based, OpenRouter's OpenAI-compatible Chat Completions API) as a third `LLM_PROVIDER` option alongside stub and gemini, mirroring GeminiLLMProvider's contract exactly.**

## Performance

- **Duration:** ~10 min
- **Completed:** 2026-07-13
- **Tasks:** 3/3
- **Files modified:** 6 (2 created, 4 modified)

## Accomplishments
- `backend/llm/openrouter.py`: new `OpenRouterLLMProvider` with deferred client construction (D-04 keyless invariant), the same five tool schemas as `gemini.py`/`stub.py` translated into OpenAI Chat Completions tool shape, `parse_constraints` and `generate_insights` both routed through `llm.translate` (D-06/D-07), and `openai.OpenAIError` mapped to the neutral `LLMProviderError` with a static message (T-pn3-03).
- `backend/llm/base.py`: registered an `openrouter` branch in `create_provider`, following the exact gemini guard pattern (raises `ValueError` mentioning "requires settings" when `settings=None`).
- `backend/settings.py`: `Settings.openrouter_api_key` (repr=False, same T-04-01 treatment as `llm_api_key`) and `Settings.openrouter_model` (default `meta-llama/llama-3.3-70b-instruct:free`), both read from `OPENROUTER_API_KEY` / `OPENROUTER_MODEL` env vars in `default_settings()`.
- `backend/pyproject.toml` / `uv.lock`: added `openai>=1.40` dependency, synced via `uv sync` (installed `openai==2.45.0`).
- `backend/tests/test_openrouter_provider.py`: 15 non-live tests mirroring `test_gemini_provider.py`'s structure with a hand-rolled OpenAI-shaped fake client, plus 2 gated `@pytest.mark.live` tests behind `OPENROUTER_API_KEY`.
- `backend/conftest.py`: surfaces `OPENROUTER_API_KEY` from a local `.env` for the live-test gate (mirrors existing `GEMINI_API_KEY` handling; `LLM_PROVIDER`/`LLM_MODEL` popping untouched).

## Task Commits

Each task was committed atomically:

1. **Task 1: Add openai dependency and extend Settings with OpenRouter config** - `ca78c98` (feat)
2. **Task 2: Implement OpenRouterLLMProvider and register it in the factory** - `ee8e951` (feat)
3. **Task 3: Mirror the Gemini provider test suite for OpenRouter** - `82ad86e` (test)

**Plan metadata:** commit pending (orchestrator handles the docs commit in Step 8)

## Files Created/Modified
- `backend/llm/openrouter.py` - New `OpenRouterLLMProvider`: tool-calling `parse_constraints`, plain-completion `generate_insights`, both mapped to `LLMProviderError` on vendor error
- `backend/tests/test_openrouter_provider.py` - Mirrored Gemini test suite: factory, translation parity, numeric coercion, error mapping, gated live tests
- `backend/llm/base.py` - `create_provider` gains `openrouter` branch; updated available-providers list and module docstring
- `backend/settings.py` - `openrouter_api_key` / `openrouter_model` fields; `default_settings()` reads both from env
- `backend/pyproject.toml`, `backend/uv.lock` - `openai>=1.40` dependency added and locked
- `backend/conftest.py` - surfaces `OPENROUTER_API_KEY` from `.env` for the `@pytest.mark.live` gate

## Decisions Made
- Verified the free tool-capable OpenRouter model slug live at implementation time (Task 2 requirement) by querying `https://openrouter.ai/api/v1/models?supported_parameters=tools` directly and cross-checking OpenRouter's Context7 docs (`/websites/openrouter_ai`) on the filter mechanism. The plan's suggested candidate, `meta-llama/llama-3.3-70b-instruct:free`, was confirmed present in the live tool-capable free-model list (18 candidates total as of 2026-07-13) and was set as the code default.
- `openrouter_model` kept as a Settings field independent of `llm_model` (per plan) since `llm_model`'s Gemini-oriented default is not a valid OpenRouter slug.
- Used `openai.OpenAIError` (SDK base error class) as the single catch target in both provider methods, matching the plan's error-mapping instruction exactly.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

`uv sync` (not `uv add`) was used to install `openai` per the plan's stated alternative ("editing pyproject then running uv sync"); this also required using `uv run python` (not the anaconda `python` on PATH) for all verification commands, since the anaconda Python lacked a working `httpx`/`openai` install. No code impact — purely a local verification-tooling note.

## User Setup Required

**External service requires manual configuration to use in local dev.** No `.env` file was edited by this plan (out of scope). To switch local/manual testing to OpenRouter, add to `backend/.env`:

```
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=<key from https://openrouter.ai/keys>
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct:free   # optional — this is the code default; env overrides it
```

The `OPENROUTER_MODEL` line is optional — omit it to use the code default (`meta-llama/llama-3.3-70b-instruct:free`), which was verified live and tool-capable at implementation time (2026-07-13) via `GET https://openrouter.ai/api/v1/models?supported_parameters=tools`. Free-tier model availability changes over time; if this slug is later retired, set `OPENROUTER_MODEL` to another slug from that same endpoint's response.

## Next Phase Readiness
- `openrouter` is fully wired end-to-end (settings → factory → provider → translate seam) and covered by unit tests; ready for local/manual live testing once a developer sets the env vars above.
- No blockers. The stub remains the keyless CI default (`LLM_PROVIDER` unset -> `"stub"`), unchanged.

---
*Phase: 260713-pn3*
*Completed: 2026-07-13*

## Self-Check: PASSED

All 6 created/modified files confirmed present on disk; all 3 task commits (ca78c98, ee8e951, 82ad86e) confirmed in git log.
