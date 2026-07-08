---
task: 260708-jov
title: Make Gemini parse_constraints reliable + load .env for live test gate
status: complete
tags: [gemini, llm, parse_constraints, conftest, dotenv, testing]
key-files:
  modified:
    - backend/llm/gemini.py
    - backend/conftest.py
commits:
  - 6e361df
  - 734a146
---

# 260708-jov: Make Gemini parse_constraints reliable Summary

Added a system instruction to `GeminiLLMProvider.parse_constraints` that
reliably steers `gemini-2.5-flash` into calling a tool for terse constraint
text (e.g. "at least 2 on Pick") while keeping AUTO tool-calling mode so
genuinely non-constraint text can still yield zero calls (NLC-03).
Separately, fixed `backend/conftest.py` to load `backend/.env` before test
collection so a `GEMINI_API_KEY` placed only in `.env` is visible to the
live test's `_HAS_KEY` gate.

## What Changed

### Task 1 — backend/llm/gemini.py

- Added module-level constant `_PARSE_SYSTEM_INSTRUCTION`, placed after
  `_TOOL_SCHEMAS`, instructing the model to call exactly one of the
  provided tools whenever the text expresses any scheduling constraint or
  change, and to respond without calling a function only when the text
  expresses no scheduling constraint at all.
- Wired `system_instruction=_PARSE_SYSTEM_INSTRUCTION` into the existing
  `GenerateContentConfig(...)` call in `parse_constraints`, alongside the
  unchanged `tools=...` and `automatic_function_calling=...` kwargs.
  Tool-calling mode remains AUTO — not switched to `ToolConfig` mode ANY —
  so non-constraint text can still legitimately produce `[]`.
- Updated the module docstring and `parse_constraints` method docstring to
  describe how the system instruction now steers tool use, without
  changing the NLC-03 AUTO-mode guarantee.
- No changes to `api_key` handling (T-04-01 unaffected).

### Task 2 — backend/conftest.py

- Added `load_dotenv(Path(__file__).resolve().parent / ".env",
  override=False)` at the top of `conftest.py`, before the `sys.path`
  mutation, mirroring `settings.py`'s path-resolution approach (relative
  to the file's own directory, real OS env vars still win).
- This runs before pytest collects `test_gemini_provider.py`, so the
  module-level `_HAS_KEY = bool(os.environ.get("GEMINI_API_KEY"))` gate
  now sees a key placed only in `backend/.env`, enabling the
  `-m live` test to actually run (previously it stayed skipped even with
  a `.env` key because `_HAS_KEY` was computed at import time before any
  `.env` load occurred).

## Verification

- `cd backend && uv run python -c "import llm.gemini; import conftest"` —
  exit 0, no output.
- `cd backend && GEMINI_API_KEY= uv run pytest -q` —
  `105 passed, 1 deselected, 1 warning in 11.13s` (matches expected: the
  live test stays deselected in the default run; all fake-client unit
  tests in `test_gemini_provider.py` pass unaffected by the system
  instruction change).
- `grep -n "system_instruction" backend/llm/gemini.py` — confirms the
  kwarg is wired into `GenerateContentConfig` at line 182.
- `grep -n "load_dotenv" backend/conftest.py` — confirms the import and
  the `load_dotenv(...)` call are present.
- Live test (`-m live`, requires a real `GEMINI_API_KEY` + network) was
  NOT run per task instructions — deferred to the orchestrator.

## Deviations from Plan

None — plan executed exactly as written. One minor implementation choice:
grouped `from pathlib import Path` alongside the existing `import os` /
`import sys` block in `conftest.py` (rather than as a separate import
group above them) to keep all imports together per project import-style
conventions, then placed the `load_dotenv(...)` call and its explanatory
comment directly below the import block, still before the `sys.path`
mutation — functionally identical to the snippet in the task
specification.

## Self-Check: PASSED

- FOUND: backend/llm/gemini.py (system_instruction kwarg present at line 182)
- FOUND: backend/conftest.py (load_dotenv call present at line 11)
- FOUND commit 6e361df (fix(260708-jov): steer Gemini parse_constraints with a system instruction)
- FOUND commit 734a146 (fix(260708-jov): load backend/.env before test collection in conftest)
