---
phase: 04-real-claude-provider-penalty-calibration
plan: 02
subsystem: llm
tags: [google-genai, gemini, function-calling, llm-provider-seam, pytest-markers, python]

# Dependency graph
requires:
  - phase: 04-real-claude-provider-penalty-calibration (plan 01)
    provides: "create_provider(name, *, settings=) factory seam + llm/translate.to_override_call + Settings.llm_provider/llm_model/llm_api_key"
provides:
  - "backend/llm/gemini.py::GeminiLLMProvider — the first real, network-backed LLMProvider (name='gemini')"
  - "the 'gemini' branch in create_provider (lazy import)"
  - "google-genai 2.10.0 runtime dependency + the registered 'live' pytest marker with addopts '-m \"not live\"'"
  - "backend/tests/test_gemini_provider.py — fake-client unit tests + one gated live parity test"
affects: [04-03-penalty-calibration]

# Tech tracking
tech-stack:
  added: ["google-genai==2.10.0"]
  patterns:
    - "Deferred client construction (_get_client, cached on first use) instead of eager construction in __init__, so a config-only provider instantiation never requires a real API key"
    - "Fake-client injection via direct setattr on provider._client (mirrors the StubEngine hand-built-fake idiom in test_api.py) — no mocking library"
    - "pytest live marker + addopts='-m \"not live\"' for default-excluded, key-gated network tests"

key-files:
  created:
    - backend/llm/gemini.py
    - backend/tests/test_gemini_provider.py
  modified:
    - backend/pyproject.toml
    - backend/llm/base.py
    - backend/uv.lock

key-decisions:
  - "Task 1 (blocking human-verify supply-chain gate for `uv add google-genai`, SUS legitimacy verdict) was approved by the human via the official Google SDK cookbook sample (github.com/google-gemini/cookbook), confirming package identity before install proceeded."
  - "GeminiLLMProvider defers genai.Client construction to first use (_get_client) rather than building it eagerly in __init__ — genai.Client(api_key=...) raises ValueError immediately when no key is resolvable, which would have broken create_provider('gemini', settings=default_settings()).name in the project's required keyless-default environment (D-04). This is a Rule 3 auto-fix: the plan's own acceptance criteria and Task 3's unit tests require this call to succeed without a key."
  - "parse_constraints uses AUTO tool-calling mode (never ANY) so non-constraint text can legitimately yield zero function calls, matching the stub's NLC-03 'no constraint found' behavior, per RESEARCH.md Pitfall 2 / Open Question 1's recommendation."
  - "AutomaticFunctionCallingConfig(disable=True) is set as defense-in-depth even though the five declared tools are schema-only FunctionDeclarations with no attached Python callables (Pitfall 1)."

patterns-established:
  - "Vendor SDK client objects requiring live credentials must defer construction past __init__ when the constructing factory (create_provider) is expected to succeed keylessly."

requirements-completed: [LLM-02, TEST-04]

coverage:
  - id: D1
    description: "google-genai 2.10.0 installed and locked; create_provider('gemini', settings=...) returns a GeminiLLMProvider named 'gemini' without requiring a real API key"
    requirement: "LLM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_gemini_provider.py#test_create_provider_gemini_returns_gemini_llm_provider"
        status: pass
      - kind: other
        ref: "uv run python -c \"from settings import default_settings; from llm.base import create_provider; p=create_provider('gemini', settings=default_settings()); print(p.name)\" -> gemini"
        status: pass
    human_judgment: false
  - id: D2
    description: "GeminiLLMProvider.parse_constraints translates the SDK's function_calls into list[OverrideCall] via the shared to_override_call helper (parity with the stub's translation path); empty/None function_calls yields []"
    requirement: "LLM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_gemini_provider.py#test_parse_constraints_translates_one_function_call, #test_parse_constraints_empty_function_calls_returns_empty_list, #test_parse_constraints_no_function_calls_list_returns_empty_list"
        status: pass
    human_judgment: false
  - id: D3
    description: "GeminiLLMProvider.generate_insights returns plain text generation output verbatim (no tools)"
    requirement: "LLM-02"
    verification:
      - kind: unit
        ref: "backend/tests/test_gemini_provider.py#test_generate_insights_returns_fake_text"
        status: pass
    human_judgment: false
  - id: D4
    description: "The 'live' pytest marker + addopts='-m \"not live\"' exclude the one live parity test from a bare pytest run by default, and it self-skips when GEMINI_API_KEY is absent"
    requirement: "TEST-04"
    verification:
      - kind: unit
        ref: "cd backend && GEMINI_API_KEY= uv run pytest -q (100 passed, 1 deselected); uv run pytest -q -m live --collect-only tests/test_gemini_provider.py selects exactly test_gemini_parse_constraints_matches_stub_parity; default --collect-only excludes it"
        status: pass
    human_judgment: false
  - id: D5
    description: "The Gemini API key never appears in any log, exception, or response string in backend/llm/gemini.py (T-04-01)"
    requirement: "LLM-02"
    verification:
      - kind: manual_procedural
        ref: "grep -n api_key backend/llm/gemini.py — all occurrences are parameter names/docstring mentions flowing only into genai.Client(api_key=...); none interpolated into f-strings, log lines, or raised exceptions"
        status: pass
    human_judgment: false

# Metrics
duration: 60min
completed: 2026-07-07
status: complete
---

# Phase 4 Plan 02: Gemini Provider (Function Calling) Summary

**Real `GeminiLLMProvider` behind the `LLMProvider` Protocol using the current `google-genai` SDK's native function calling for `parse_constraints` and plain text generation for `generate_insights`, gated by a checkpoint-approved `uv add google-genai` install and a default-excluded `@pytest.mark.live` parity test.**

## Performance

- **Duration:** 60 min
- **Started:** 2026-07-07T21:44:12+07:00 (approx, first commit)
- **Completed:** 2026-07-07T22:44:39+07:00
- **Tasks:** 3 (Task 1 checkpoint pre-approved by human before this session)
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments

- Task 1's blocking `checkpoint:human-verify` supply-chain gate for `google-genai` (SUS legitimacy verdict — automated check flagged "too-new"/"unknown-downloads", a false positive per RESEARCH.md) was approved by the human via the official Google SDK cookbook sample before this session; `uv add google-genai` installed and locked `google-genai==2.10.0`.
- Registered the `live` pytest marker + `addopts = "-m \"not live\""` in `backend/pyproject.toml` so a bare `pytest` excludes network-backed tests by default.
- Added the `"gemini"` branch to `create_provider` in `backend/llm/base.py` (lazy import, mirrors the stub branch); unknown-provider error text now lists both `stub` and `gemini`.
- Implemented `backend/llm/gemini.py::GeminiLLMProvider`: five `types.FunctionDeclaration` tool schemas mirroring the stub's arg shapes, `parse_constraints` (AUTO tool-calling mode, `AutomaticFunctionCallingConfig(disable=True)`, iterates `response.function_calls`, routes each `(name, args)` pair through the shared `to_override_call`), and `generate_insights` (tool-less `generate_content` call with a grounding-aware prompt, returns `response.text`).
- Added `backend/tests/test_gemini_provider.py`: 5 fake-client unit tests (no network) covering provider creation, one-function-call translation, empty/`None` function_calls, and insight-text passthrough, plus one `@pytest.mark.live` D-06 reframed-parity test gated on `GEMINI_API_KEY`.
- Full non-live suite: 100 passed, 1 deselected (the live test), with no `GEMINI_API_KEY` set — keyless CI invariant holds.

## Task Commits

Each task was committed atomically:

1. **Task 1: Confirm google-genai package legitimacy before install (SUS verdict)** - pre-approved by human before this session (no commit; checkpoint gate only, no code written)
2. **Task 2: Install the SDK, register the gemini branch, and implement GeminiLLMProvider** - `4749135` (feat)
3. **Task 3: Gemini unit tests (fake client) + the one gated live parity test (TEST-04)** - `54f0c83` (test)

**Plan metadata:** (this commit, made after this SUMMARY)

## Files Created/Modified

- `backend/llm/gemini.py` - New `GeminiLLMProvider` (name="gemini"): five `FunctionDeclaration` tool schemas, `parse_constraints` (function-calling, AUTO mode), `generate_insights` (plain text generation); deferred `genai.Client` construction via `_get_client()`.
- `backend/llm/base.py` - Added the `"gemini"` branch to `create_provider`; unknown-provider error text now lists `['stub', 'gemini']`.
- `backend/pyproject.toml` - Added `google-genai>=2.10.0` to `[project].dependencies` (via `uv add`); registered `markers = ["live: ..."]` and `addopts = "-m \"not live\""` in `[tool.pytest.ini_options]`.
- `backend/uv.lock` - Locked `google-genai` 2.10.0 and its transitive dependencies (google-auth, cryptography, requests, tenacity, etc.).
- `backend/tests/test_gemini_provider.py` - New: fake-client unit tests (`_FakeFunctionCall`/`_FakeResponse`/`_FakeModels`/`_FakeClient` mirroring the `StubEngine` idiom) + the one gated `@pytest.mark.live` parity test.

## Decisions Made

- `GeminiLLMProvider.__init__` no longer constructs `genai.Client` eagerly. `genai.Client(api_key=...)` raises `ValueError` immediately whenever the resolved key is falsy (confirmed empirically: both `api_key=None` and `api_key=""` raise identically, and no `GOOGLE_API_KEY`/`GEMINI_API_KEY` fallback exists in this environment). The plan's own Task 2 verify command and Task 3's `test_create_provider_gemini_returns_gemini_llm_provider` both call `create_provider("gemini", settings=default_settings())` with no key set, and the project's D-04 "default stub, keyless CI" invariant requires this to succeed. Construction is now deferred to a `_get_client()` helper, cached on first use — a real key is only required once an actual API call is attempted, which matches real usage (production always threads a real `settings.llm_api_key`). Task 3's fake-client tests inject `provider._client = fake` directly (unaffected by this change, since `_client` remains a plain instance attribute).
- `parse_constraints` uses AUTO tool-calling mode (not ANY) per RESEARCH.md's recommendation (Pitfall 2 / Open Question 1) so genuinely non-constraint text can yield zero function calls, matching the stub's NLC-03 behavior; the live parity test only exercises unambiguous text ("at least 2 on Pick"), so AUTO mode does not risk flaking that assertion.
- Two `FunctionDeclaration` schema lines were wrapped to stay within the project's ~100-char line-length convention (CLAUDE.md).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Deferred `genai.Client` construction to first use**
- **Found during:** Task 2 verification (`create_provider('gemini', settings=default_settings()).name`)
- **Issue:** `GeminiLLMProvider.__init__` as literally specified in the plan (`genai.Client(api_key=api_key)` constructed eagerly) raises `ValueError: No API key was provided` whenever no `GEMINI_API_KEY` is set — which is exactly the keyless-CI environment this executor ran in, and exactly the environment the plan's own acceptance criteria (`create_provider("gemini", settings=default_settings()).name == "gemini"`, run with no key prefix) and Task 3's `test_create_provider_gemini_returns_gemini_llm_provider` unit test require to pass.
- **Fix:** Added a `_get_client()` helper that lazily constructs and caches `genai.Client(api_key=self._api_key)` on first use; `__init__` now only stores `api_key`/`model` and sets `self._client = None`. `parse_constraints`/`generate_insights` call `self._get_client()` instead of `self._client` directly.
- **Files modified:** `backend/llm/gemini.py`
- **Verification:** `uv run python -c "...create_provider('gemini', settings=default_settings()).name"` prints `gemini` with no key set; `GEMINI_API_KEY= uv run pytest -q` — 100 passed, 1 deselected.
- **Committed in:** `4749135` (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary to satisfy the plan's own keyless-CI acceptance criteria; no behavior change for real (keyed) usage — the client is still constructed with the same `api_key`/`model`, just on first actual API call instead of at construction time.

## Issues Encountered

None beyond the deviation above.

## User Setup Required

**External service configuration is optional, not required for CI.** To exercise the real Gemini provider or the one gated live test:
- Get a free-tier API key from Google AI Studio ("Get API key").
- Set `GEMINI_API_KEY` in the environment.
- Optionally set `LLM_PROVIDER=gemini` to select the real provider for manual runs, or leave unset (`stub` default) — CI and the default test suite never require this.
- Run `cd backend && uv run pytest -q -m live` to exercise the live parity test.

No `.env` file or dashboard configuration exists in this project (env-var only, per `backend/settings.py`); nothing further to configure.

## Next Phase Readiness

- LLM-02 (real provider behind the seam) and TEST-04 (one gated live test) are both fully satisfied. Phase 4's other requirement, ENG-04/penalty calibration (plan 04-03), was already executed in a prior session (wave-parallel, independent of this plan) — `git log` shows `04-03-PLAN.md` completed before this plan.
- Switching `LLM_PROVIDER=gemini` + `GEMINI_API_KEY=<key>` is pure config — no service or router file was touched in this plan, proving the Phase 4 plan 01 seam holds end to end for a real provider.
- No blockers. The phase's remaining work (if any) is limited to whatever plan 04-03 already covered plus any phase-level wrap-up.

---
*Phase: 04-real-claude-provider-penalty-calibration*
*Completed: 2026-07-07*

## Self-Check: PASSED

- FOUND: backend/llm/gemini.py
- FOUND: backend/tests/test_gemini_provider.py
- FOUND: 4749135 (Task 2 commit)
- FOUND: 54f0c83 (Task 3 commit)
