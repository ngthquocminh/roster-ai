---
phase: 04-real-claude-provider-penalty-calibration
plan: 01
subsystem: llm
tags: [llm-provider-seam, config, fastapi-di, settings, python]

# Dependency graph
requires:
  - phase: 02-full-tool-set-and-safe-validation
    provides: StubLLMProvider + LLMProvider Protocol + OverrideCall domain type
provides:
  - "backend/llm/translate.py::to_override_call — single provider-neutral translation point"
  - "Settings.llm_provider/llm_model/llm_api_key + env-driven default_settings()"
  - "create_provider(name, *, settings=None) factory signature ready for a 'gemini' branch"
  - "get_llm_provider() reads settings.llm_provider via Depends(get_settings)"
affects: [04-02-gemini-provider, 04-03-penalty-calibration]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Shared translation helper (llm/translate.py) mirrored on domain/overrides.override_id"
    - "Config-driven factory selection mirroring engine/base.py's create_engine lazy-import registry"

key-files:
  created:
    - backend/llm/translate.py
  modified:
    - backend/llm/stub.py
    - backend/llm/base.py
    - backend/settings.py
    - backend/api/deps.py
    - backend/tests/test_llm_provider.py

key-decisions:
  - "to_override_call takes (tool_name, args) not a vendor dict — callers unpack vendor payload shape before calling it (D-07/D-08/D-09)"
  - "create_provider(name, *, settings=None) accepts settings as a keyword-only optional arg now so the stub branch (which ignores it) and a future gemini branch (which needs it) share one signature"
  - "get_llm_provider requires an explicit Settings argument (via Depends(get_settings) in production, or an explicit default_settings() in tests) — the FastAPI Depends sentinel is never passed to create_provider"

patterns-established:
  - "Provider-neutral translation boundary: no vendor payload (Claude tool_use dict, future Gemini FunctionCall) may cross into domain.OverrideCall except through llm/translate.to_override_call"

requirements-completed: [LLM-02]

coverage:
  - id: D1
    description: "Shared to_override_call helper extracted; stub's five call sites route through it; private _to_override_call removed"
    requirement: "LLM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_llm_provider.py (13 pre-existing tests, unchanged assertions)"
        status: pass
    human_judgment: false
  - id: D2
    description: "Settings carries llm_provider/llm_model/llm_api_key, env-driven, defaulting to stub/gemini-2.5-flash/None"
    requirement: "LLM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_llm_provider.py#test_default_settings_llm_defaults_keyless"
        status: pass
    human_judgment: false
  - id: D3
    description: "get_llm_provider is env-driven via settings.llm_provider; create_provider accepts a settings kwarg; no service/route code changed"
    requirement: "LLM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_llm_provider.py#test_get_llm_provider_respects_env, #test_create_provider_threads_settings"
        status: pass
      - kind: other
        ref: "git diff --name-only across the three task commits touches no file under backend/services/ or backend/api/routers/"
        status: pass
    human_judgment: false
  - id: D4
    description: "Full non-live suite stays green with no GEMINI_API_KEY set (keyless CI)"
    requirement: "LLM-02"
    verification:
      - kind: unit
        ref: "cd backend && GEMINI_API_KEY= uv run pytest -q -k \"not live\" (92 passed)"
        status: pass
    human_judgment: false

duration: 8min
completed: 2026-07-07
status: complete
---

# Phase 4 Plan 01: Config-Selectable Provider + Shared Translation Summary

**`LLM_PROVIDER` env var (default `stub`) now selects the backend through a settings-threaded `create_provider`/`get_llm_provider` seam, and every `OverrideCall` — stub today, any future provider tomorrow — is produced by one shared `llm/translate.to_override_call` function.**

## Performance

- **Duration:** 8 min
- **Started:** 2026-07-07T09:24:00+07:00 (approx, first commit 09:25:54)
- **Completed:** 2026-07-07T09:28:01+07:00
- **Tasks:** 3
- **Files modified:** 6 (1 created, 5 modified)

## Accomplishments
- Extracted `backend/llm/translate.py::to_override_call(tool_name, args)` as the single provider-neutral translation point; `StubLLMProvider`'s five call sites and the private `_to_override_call` were replaced with calls into the shared helper (D-07).
- `Settings` gained `llm_provider` / `llm_model` / `llm_api_key`, read from `LLM_PROVIDER` (default `"stub"`), `LLM_MODEL` (default `"gemini-2.5-flash"`), and `GEMINI_API_KEY` (default `None`) in `default_settings()`.
- `create_provider(name: str, *, settings=None)` in `backend/llm/base.py` accepts (but the stub branch ignores) settings, ready for a `"gemini"` branch in a later plan; unknown names still raise `ValueError`.
- `get_llm_provider` in `backend/api/deps.py` now resolves `Settings` via `Depends(get_settings)` and calls `create_provider(settings.llm_provider, settings=settings)` — no service or router file changed, proving the seam holds (LLM-02 criterion 1).
- Full non-live suite (92 tests) passes with no `GEMINI_API_KEY` set.

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract the shared to_override_call helper and re-point the stub (D-07)** - `5c7e168` (feat)
2. **Task 2: Config-driven provider selection (Settings + deps + factory signature, D-04/D-05)** - `a77830c` (feat)
3. **Task 3: Seam tests — keyless default + env-driven selection wiring** - `a84df8b` (test)

**Plan metadata:** (this commit, made after this SUMMARY)

## Files Created/Modified
- `backend/llm/translate.py` - New shared `to_override_call(tool_name, args) -> OverrideCall`; the single provider-neutral translation point (D-07).
- `backend/llm/stub.py` - Removed private `_to_override_call`; all five call sites now call `llm.translate.to_override_call`; docstring updated to reference the shared helper.
- `backend/llm/base.py` - `create_provider(name: str, *, settings=None)`; docstring reworded to be provider-generic instead of Claude-specific.
- `backend/settings.py` - `Settings` gained `llm_provider`/`llm_model`/`llm_api_key`; `default_settings()` reads the three new env vars; docstring reworded (no longer filesystem-only).
- `backend/api/deps.py` - `get_llm_provider` now takes `settings: Settings = Depends(get_settings)` and threads `settings.llm_provider` into `create_provider`.
- `backend/tests/test_llm_provider.py` - `test_get_llm_provider_returns_stub`/`test_get_llm_provider_parse_constraints_works` updated to pass an explicit `default_settings()`; added `test_default_settings_llm_defaults_keyless`, `test_get_llm_provider_respects_env`, `test_create_provider_threads_settings`.

## Decisions Made
- `to_override_call` takes `(tool_name, args)`, never a vendor-shaped dict — callers (stub today, Gemini in 04-02) must unpack their own payload shape first, upholding D-08/D-09 and Phase 4 D-02.
- `create_provider`'s new `settings` parameter is keyword-only and optional (`settings=None`) so the current stub-only call sites (including the pre-existing `test_create_provider_stub_returns_stub_llm_provider` test, which calls `create_provider("stub")` with no settings) keep working unchanged.
- `get_llm_provider` requires an explicit `Settings` object; the FastAPI `Depends` sentinel is never passed through to `create_provider` — tests now always construct `default_settings()` explicitly, matching the LOAD-BEARING NOTE in the plan.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required. No API key is consumed yet (the `"gemini"` branch and any real network call land in plan 04-02).

## Next Phase Readiness

- The seam is proven end to end: `LLM_PROVIDER` config selects the backend, defaults to `stub`, and the full non-live suite (92 tests) is green with no `GEMINI_API_KEY` set.
- `create_provider`'s `settings` kwarg and `llm/translate.to_override_call` are in place for plan 04-02 to add a `"gemini"` branch (`backend/llm/gemini.py`) that constructs a real provider from `settings.llm_api_key`/`settings.llm_model` and reuses the same shared translation helper.
- No blockers.

---
*Phase: 04-real-claude-provider-penalty-calibration*
*Completed: 2026-07-07*

## Self-Check: PASSED

- FOUND: backend/llm/translate.py
- FOUND: 5c7e168 (Task 1 commit)
- FOUND: a77830c (Task 2 commit)
- FOUND: a84df8b (Task 3 commit)
