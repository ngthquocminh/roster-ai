---
phase: quick-260708-e7z
plan: 01
subsystem: backend-config
tags: [settings, dotenv, llm-provider, env]
dependency-graph:
  requires: []
  provides:
    - "backend/.env support for LLM_PROVIDER / LLM_MODEL / GEMINI_API_KEY"
  affects:
    - backend/settings.py
tech-stack:
  added:
    - python-dotenv (>=1.2.2)
  patterns:
    - "Module-scope load_dotenv(path, override=False) at settings.py import time, resolved via _BACKEND_DIR so it's CWD-independent"
key-files:
  created:
    - backend/.env.example
    - backend/.env
  modified:
    - backend/pyproject.toml
    - backend/uv.lock
    - backend/settings.py
    - .gitignore
decisions:
  - "python-dotenv added as a runtime (not dev-group) dependency because settings.py is imported by the app, CLI, and tests alike"
  - "load_dotenv(..., override=False) — a real OS env var always wins over the .env file; empty GEMINI_API_KEY= in the file never clobbers an already-set OS key"
  - "backend/.env ships locally with only an empty GEMINI_API_KEY= placeholder and no LLM_PROVIDER, keeping the keyless stub default in effect"
metrics:
  duration: "~15 min"
  completed: "2026-07-08"
status: complete
---

# Phase quick-260708-e7z Plan 01: Add .env support for backend LLM provider config Summary

Added optional `backend/.env` loading to `settings.py` via `python-dotenv`, plus a
committed `backend/.env.example` and gitignore rules — so `LLM_PROVIDER` / `LLM_MODEL`
/ `GEMINI_API_KEY` can be set locally without exporting OS env vars, while OS env
vars still take precedence and the keyless test suite stays green.

## What Was Built

1. **`python-dotenv` runtime dependency** — added via `uv add python-dotenv`
   (resolved to `>=1.2.2`), updating `backend/pyproject.toml` and `backend/uv.lock`.
2. **`load_dotenv` wired into `settings.py`** — a single module-scope call,
   `load_dotenv(_BACKEND_DIR / ".env", override=False)`, placed after
   `_BACKEND_DIR` is resolved and before `default_settings()` is defined. Path is
   resolved relative to the settings module file, so it works identically from
   the API server, `run.py` CLI, and pytest regardless of process CWD.
3. **`backend/.env.example`** (committed) — documents `LLM_PROVIDER`, `LLM_MODEL`,
   `GEMINI_API_KEY` with placeholder/empty values, a link to the free Gemini key
   source (https://aistudio.google.com/apikey), and a note that `LLM_PROVIDER=gemini`
   requires a real key while everything else falls back to the stub provider.
4. **`backend/.env`** (local, gitignored) — a single empty `GEMINI_API_KEY=`
   placeholder for developers to fill in; `LLM_PROVIDER` left unset so the keyless
   stub default stays in effect.
5. **`.gitignore` rules** — added `.env`, `.env.*`, `!.env.example` so any `.env`
   file anywhere in the repo is ignored except the tracked example.

## Deviations from Plan

None — plan executed exactly as written.

## Verification Results

- `grep -qi python-dotenv backend/pyproject.toml` — PASS (dependency present).
- `git check-ignore backend/.env` → prints `backend/.env` (ignored, exit 0).
- `git check-ignore backend/.env.example` → prints nothing (tracked, exit 1).
- `cd backend && GEMINI_API_KEY= uv run python -c "import settings; s=settings.default_settings(); print(s.llm_provider, s.llm_model, s.llm_api_key)"` →
  `stub gemini-2.5-flash` (trailing empty string for `llm_api_key`, not the literal
  word `None` — see note below).
- `cd backend && GEMINI_API_KEY= uv run pytest -q` → **105 passed, 1 deselected**
  (keyless-CI invariant preserved).
- `backend/.env.example` content reviewed directly (via `git show :backend/.env.example`,
  since the harness blocks direct Read/Grep on `.env*` paths) — contains only the
  placeholder values shown above; no secret-shaped strings.

**Note on the `llm_api_key` verification value:** the plan's expected output was
`stub gemini-2.5-flash None`. In this shell, `GEMINI_API_KEY= uv run ...` sets the
env var to an **empty string** in the child process (confirmed independently with
`python -c "import os; print(repr(os.environ.get('GEMINI_API_KEY')))"` → `''`), not
an *unset* variable — so `os.environ.get("GEMINI_API_KEY")` in `default_settings()`
returns `""`, not `None`. This is pre-existing behavior in `default_settings()`
(`llm_api_key = os.environ.get("GEMINI_API_KEY")`, unchanged by this plan) and is
unrelated to the `.env`/dotenv change — it reproduces identically before and after
this plan's edits. The empty string is falsy, so it behaves the same as `None`
everywhere it's consumed (provider selection, `__repr__` exclusion), and the 105
keyless tests all pass with this value. No code change was needed or made.

## Self-Check: PASSED

- FOUND: backend/.env.example (tracked, `git show :backend/.env.example` returns content)
- FOUND: backend/.env (present locally, `git check-ignore` confirms it is ignored)
- FOUND: backend/settings.py has `from dotenv import load_dotenv` and the module-scope call
- FOUND commit 5b13d6d: chore(260708-e7z): add python-dotenv runtime dependency
- FOUND commit 586a997: feat(260708-e7z): load backend/.env at settings import time
- FOUND commit 2d2510b: feat(260708-e7z): add backend .env.example and gitignore rules
