---
task: 260709-m9m
title: Map LLM provider errors to a clean 503 in POST /constraints
status: complete
tags: [gemini, llm, error-handling, fastapi, http-status, testing]
key-files:
  created: []
  modified:
    - backend/llm/base.py
    - backend/llm/gemini.py
    - backend/api/routers/constraints.py
    - backend/tests/test_constraints_api.py
    - backend/tests/test_gemini_provider.py
    - backend/conftest.py
commits:
  - 7b0440a
  - f307c40
  - 9ca6d44
  - b4237a3
  - 047a5f2
  - 8d0c785
---

# 260709-m9m: Map LLM provider errors to a clean 503 Summary

When the real Gemini provider's backend call fails (bad key, quota, overload,
network), `POST /constraints` previously let the raw `google.genai.errors`
exception propagate, producing a bare `500 Internal Server Error` with a stack
trace. Introduced a provider-neutral `LLMProviderError` on the `LLMProvider`
seam, wrapped both Gemini SDK network calls to raise it instead of the vendor
exception type, and mapped it to a clean `503` in the `/constraints` route —
same "no vendor payload/exception crosses the boundary" principle as D-02.

## What Changed

### Task 1 — backend/llm/base.py

- Added `class LLMProviderError(RuntimeError)` as a module-level export, with
  a docstring explaining its purpose: provider-neutral so vendor exception
  types never cross the `LLMProvider` seam; callers map it to an appropriate
  HTTP status.

### Task 2 — backend/llm/gemini.py

- Added `from google.genai import errors as genai_errors` and
  `from llm.base import LLMProviderError` (no circular import — `base.py`
  only lazy-imports providers inside `create_provider`).
- Wrapped the `generate_content(...)` call in `parse_constraints` in
  `try/except genai_errors.APIError as exc: raise LLMProviderError("Gemini
  request failed") from exc`. `APIError` is the base class of
  `ClientError`/`ServerError`, so this covers 400/429/503-class vendor
  errors.
- Applied the identical wrap to the `generate_content(...)` call in
  `generate_insights`.
- The raised message is a fixed generic string (`"Gemini request failed"`)
  with no interpolation of the api_key, raw exception text, or response body
  (T-04-01); `raise ... from exc` preserves the original traceback for
  server-side logs only.

### Task 3 — backend/api/routers/constraints.py

- Imported `LLMProviderError` alongside `LLMProvider`.
- Added `except LLMProviderError:` after the existing `except LookupError`
  arm, raising `HTTPException(status_code=503, detail="The scheduling
  assistant is temporarily unavailable. Please try again shortly.")`.
- Added `503: {"description": "LLM provider unavailable"}` to the route's
  `responses={...}` dict.
- Confirmed `insight_service.py`'s existing `except Exception as exc:` at
  line 148 still catches `LLMProviderError` (it is a `RuntimeError`
  subclass) — no change needed there per task instructions.

### Task 4 — backend/tests/test_constraints_api.py

- Added `test_post_constraints_provider_failure_returns_503`, mirroring the
  existing `client`/`scenario_id` fixture pattern but with an inline
  `_FailingProvider` (raises `LLMProviderError("boom")` from both
  `parse_constraints` and `generate_insights`) injected via
  `app.dependency_overrides[get_llm_provider]`. Asserts `resp.status_code ==
  503` and the exact detail string.

### Task 5 — backend/tests/test_gemini_provider.py

- Added `_FailingModels`/`_FailingClient` fakes whose `generate_content`
  raises a real `google.genai.errors.ClientError` instance (constructed as
  `ClientError(400, {"error": {"message": "bad key", "status":
  "INVALID_ARGUMENT"}})` — verified this constructor signature against the
  installed SDK before writing the test).
- Added `test_parse_constraints_maps_vendor_api_error_to_llm_provider_error`,
  asserting `provider.parse_constraints(...)` raises `LLMProviderError` when
  the fake `_client` raises the vendor `ClientError`. Network-free.

## Verification

- `cd backend && uv run python -c "import llm.gemini, llm.base,
  api.routers.constraints, services.constraint_service"` — exit 0.
- `cd backend && uv run pytest -q -m "not live"` (bare — no forced
  `LLM_PROVIDER`) — `107 passed, 1 deselected, 1 warning`. Green even with
  `LLM_PROVIDER=gemini` present in a dev `.env`, after the conftest
  determinism fix (see Deviations). 105 baseline + 2 new tests; the live
  test stays deselected.
- `grep -n "LLMProviderError" backend/llm/base.py backend/llm/gemini.py
  backend/api/routers/constraints.py` — confirms the type is defined
  (`base.py:15`), raised twice (`gemini.py:189`, `gemini.py:209`), imported
  and caught (`constraints.py:16`, `constraints.py:47`).

## Deviations from Plan

**1. [Rule 1 — Bug, FIXED] `.env` `LLM_PROVIDER` leaked into the test process,
breaking the stub-default test (`test_get_llm_provider_returns_stub`)**
- **Found during:** Verification (Task 5), then fixed under a follow-up
  coordinator directive.
- **Issue:** A dev's gitignored `backend/.env` (from prior quick tasks
  260708-e7z/260708-jov) sets `LLM_PROVIDER=gemini`. Two independent
  import-time `load_dotenv(backend/.env, override=False)` calls pulled that
  value into `os.environ` during tests: (a) `conftest.py` (added by
  260708-jov) and, more subtly, (b) `settings.py` line 23, which loads `.env`
  at import time for the real app. With `LLM_PROVIDER=gemini` in the env,
  `default_settings()` resolved to the gemini provider, so
  `test_get_llm_provider_returns_stub` failed with
  `assert 'gemini' == 'stub'` (bare `uv run pytest -q -m "not live"` →
  `1 failed, 106 passed`). This broke the stub-only-CI invariant.
- **Fix:** Rewrote `backend/conftest.py` to (1) surface ONLY `GEMINI_API_KEY`
  from the local `.env` via `dotenv_values` (read without mutating
  `os.environ`) so the `@pytest.mark.live` gate still detects a dev's key,
  and (2) trigger `settings.py`'s one-time import-time `load_dotenv` and then
  `os.environ.pop("LLM_PROVIDER")` / `pop("LLM_MODEL")` so every test observes
  the keyless `stub` default regardless of a dev's `.env`. `settings.py` is
  left loading `.env` for the real app (API server / `run.py` CLI) — the
  scoping is test-process only. `.env` files themselves were not touched.
- **Files modified:** `backend/conftest.py`
- **Verification:** bare `cd backend && uv run pytest -q -m "not live"` →
  `107 passed, 1 deselected, 1 warning` (stub-default test green again even
  with `LLM_PROVIDER=gemini` in `.env`);
  `uv run python -c "import conftest, os; print(bool(os.environ.get('GEMINI_API_KEY')), os.environ.get('LLM_PROVIDER'))"`
  → `True None` (live gate sees the key; provider no longer leaks).
- **Committed in:** `8d0c785`

---

**Total deviations:** 1 auto-fixed (Rule 1 — test-determinism bug: a `.env`
value leaking into the test process via two import-time `load_dotenv` calls,
scoped out in the test harness without altering production `.env` loading).
**Impact on plan:** None — the core 503-mapping implementation is complete and
verified, and the test suite is now deterministic under a keyless/stub CI
configuration regardless of a developer's local `.env`.

## Issues Encountered

The initial verification surfaced a pre-existing test-determinism bug (a dev
`.env` leaking `LLM_PROVIDER` into the test process via two import-time
`load_dotenv` calls — `conftest.py` and `settings.py`). Resolved in the test
harness (`conftest.py`) per the deviation above; production `.env` loading in
`settings.py` was intentionally left intact.

## Self-Check: PASSED

- FOUND: backend/llm/base.py (LLMProviderError defined)
- FOUND: backend/llm/gemini.py (both network calls wrapped)
- FOUND: backend/api/routers/constraints.py (except LLMProviderError -> 503)
- FOUND: backend/tests/test_constraints_api.py (test_post_constraints_provider_failure_returns_503)
- FOUND: backend/tests/test_gemini_provider.py (test_parse_constraints_maps_vendor_api_error_to_llm_provider_error)
- FOUND: backend/conftest.py (dotenv_values key-only surface + settings-import provider/model pop)
- FOUND commit 7b0440a (feat(260709-m9m): add provider-neutral LLMProviderError type)
- FOUND commit f307c40 (feat(260709-m9m): wrap Gemini SDK calls to raise LLMProviderError)
- FOUND commit 9ca6d44 (feat(260709-m9m): map LLMProviderError to a clean 503 in /constraints)
- FOUND commit b4237a3 (test(260709-m9m): assert provider failure yields 503, not 500)
- FOUND commit 047a5f2 (test(260709-m9m): assert vendor APIError maps to LLMProviderError)
- FOUND commit 8d0c785 (fix(260709-m9m): scope conftest .env load to GEMINI_API_KEY only)
