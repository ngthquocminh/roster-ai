---
phase: 04-real-claude-provider-penalty-calibration
reviewed: 2026-07-08T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - backend/api/deps.py
  - backend/config/constants.py
  - backend/llm/base.py
  - backend/llm/gemini.py
  - backend/llm/stub.py
  - backend/llm/translate.py
  - backend/pyproject.toml
  - backend/scripts/calibrate_penalties.py
  - backend/settings.py
  - backend/tests/test_gemini_provider.py
  - backend/tests/test_llm_provider.py
  - backend/tests/test_penalty_calibration.py
findings:
  critical: 0
  warning: 4
  info: 2
  total: 6
status: issues_found
---

# Phase 4: Code Review Report

**Reviewed:** 2026-07-08T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

This phase adds the first network-backed `LLMProvider` (`GeminiLLMProvider`),
env-driven provider selection in `settings.py`/`deps.py`, a shared translation
helper (`llm/translate.py`) refactored out of the stub, penalty-constant
calibration in `config/constants.py` plus a derivation script, and the
supporting test suite.

The core phase invariants hold and were verified:

- **T-04-01 (key never logged/interpolated):** Inside `gemini.py` the API key
  only ever flows into `genai.Client(api_key=self._api_key)` — no f-string, log
  line, or exception message references it. The `create_provider` error message
  interpolates the *provider name*, not the key. **Upheld.**
- **D-02 (no vendor payload crosses the boundary):** `parse_constraints` unpacks
  each vendor `FunctionCall` to a plain `(name, dict(args))` pair before
  `to_override_call`; only `list[OverrideCall]` is returned. **Upheld.**
- **Keyless-CI invariant:** client construction is deferred to `_get_client`, so
  `create_provider("gemini")` needs no key; the single live test is
  `@pytest.mark.live` + `skipif(not _HAS_KEY)`, and `addopts = -m "not live"`
  excludes it by default. **Upheld.**
- **Parity substrate (D-07):** stub and gemini both route through the same
  `to_override_call`, producing `ov_`-prefixed content-hash ids. **Upheld at the
  translation seam**, with one residual gap noted in WR-03.
- **Calibration monkeypatch correctness:** `engine/cpsat/builder.py` reads
  `C.MIN_WORKERS_PENALTY` etc. via live module-attribute access (`from config
  import constants as C`), so `calibrate_penalties.run_case`'s `setattr(C, ...)`
  genuinely takes effect and is restored in `finally`. **Correct.**

No blocker-severity defects were proven. Four warnings and two info items follow.

## Warnings

### WR-01: `generate_insights` can return `None`, violating the `-> str` Protocol contract

**File:** `backend/llm/gemini.py:169-178`
**Issue:** `generate_insights` returns `response.text` unguarded. In the
`google-genai` SDK, `response.text` returns `None` when the model produces no
text part — e.g. a safety-blocked response, an empty candidate, or a
finish-reason other than STOP. The `LLMProvider` Protocol (`llm/base.py:17`)
and the stub both promise `-> str`. Returning `None` breaks that contract and
propagates a non-string into the downstream D-06 grounding guard / insight
persistence, where string operations (`.strip()`, membership checks) will raise
`AttributeError` on an otherwise-successful solve. The docstring even names the
grounding guard as the enforcement net, but that guard assumes a string input.
**Fix:**
```python
text = self._get_client().models.generate_content(model=self._model, contents=prompt).text
return text or ""   # never return None; empty string degrades gracefully
```
(Consider surfacing the blocked/empty case explicitly rather than silently
emptying, but at minimum guarantee a `str`.)

### WR-02: `create_provider("gemini")` without `settings` fails with an opaque `AttributeError`

**File:** `backend/llm/base.py:23,28-30`
**Issue:** The factory signature defaults `settings=None`, but the `gemini`
branch immediately dereferences `settings.llm_api_key` / `settings.llm_model`.
Calling `create_provider("gemini")` (no settings) raises
`AttributeError: 'NoneType' object has no attribute 'llm_api_key'` — an unclear
error that leaks an implementation detail instead of a caller-actionable
message. The stub branch tolerates `settings=None`, so the asymmetry is easy to
trip in scripts/tests.
**Fix:**
```python
if name == "gemini":
    if settings is None:
        raise ValueError("create_provider('gemini') requires settings=...")
    from llm.gemini import GeminiLLMProvider
    return GeminiLLMProvider(api_key=settings.llm_api_key, model=settings.llm_model)
```

### WR-03: Gemini `parse_constraints` args are not normalized, so parity with the stub is not guaranteed

**File:** `backend/llm/gemini.py:166-167`
**Issue:** The stub coerces argument types deterministically (`n = int(...)`,
`factor = float(...)`, `max_hours = float(...)`, `day` -> `int`). The Gemini
path passes `dict(fc.args)` straight through with no coercion. Two consequences:
1. **Parity/hash divergence:** if the model returns `n` as `2.0` (numbers can
   come back as float even under an `"integer"` schema), `override_id` hashes
   `{"n": 2.0}` vs the stub's `{"n": 2}`, yielding a *different* `OverrideCall.id`
   for the same constraint — breaking the idempotency/parity the phase requires
   ("same OverrideCall output shape").
2. **`TypeError` on a malformed call:** `dict(fc.args)` raises if `fc.args` is
   `None` (a function call emitted with no arguments), and that exception is
   unhandled inside `parse_constraints`.
**Fix:** guard `fc.args` and normalize per-tool arg types before translating,
e.g.:
```python
calls = response.function_calls or []
return [to_override_call(fc.name, _normalize(fc.name, dict(fc.args or {}))) for fc in calls]
```
where `_normalize` casts `n`/`day` to `int` and `factor`/`max_hours` to `float`
to match the stub exactly.

### WR-04: `Settings` auto-generated `__repr__` exposes `llm_api_key`

**File:** `backend/settings.py:17-23`
**Issue:** `@dataclass(frozen=True)` synthesizes a `__repr__` that includes every
field, so `repr(settings)` / any log line or unhandled exception that renders a
`Settings` instance prints
`Settings(..., llm_api_key='AIza...')` in cleartext. Given the phase's explicit
T-04-01 mandate that the key never reach a string/log, storing it in a dataclass
whose default repr serializes it is a latent secret-leak vector (FastAPI
dependency errors and debug logging both render argument reprs).
**Fix:**
```python
llm_api_key: str | None = field(repr=False, default=None)  # keep out of repr/logs
```
(import `field` from `dataclasses`).

## Info

### IN-01: Constants docstring cites a 5,000,000 sweep the committed script does not perform

**File:** `backend/config/constants.py:46-49` and `backend/scripts/calibrate_penalties.py:31`
**Issue:** The `MIN_WORKERS_PENALTY` docstring states "Sweeping this scale up to
5_000_000 (50x) against the same fixture/override produced no change," but the
committed `SCALES = (10_000, 50_000, 100_000, 250_000, 500_000)` tops out at
500_000 (5x). The derivation cited in the docstring is not reproducible with the
checked-in script, weakening the calibration audit trail.
**Fix:** either extend `SCALES` to include the values the docstring claims were
swept, or reword the docstring to match the committed sweep range.

### IN-02: Insight prompt interpolates a raw Python dict via `str.format`

**File:** `backend/llm/gemini.py:176`
**Issue:** `_INSIGHT_PROMPT_TEMPLATE.format(summary=summary)` renders the summary
as its Python `repr` (`{'metrics': {...}}`), embedding Python quoting/`None`
tokens into the prompt rather than a clean JSON or bullet rendering. This is
functionally harmless but reduces prompt quality/legibility for the model
compared to the stub's structured rendering.
**Fix:** render the summary explicitly (e.g. `json.dumps(summary, indent=2)`)
before interpolation.

---

_Reviewed: 2026-07-08T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
