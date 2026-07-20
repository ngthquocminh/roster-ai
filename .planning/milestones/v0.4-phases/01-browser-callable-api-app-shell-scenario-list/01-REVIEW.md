---
status: partial
phase: 01-browser-callable-api-app-shell-scenario-list
depth: standard (agent interrupted; orchestrator inline security pass substituted)
files_reviewed: 5
findings:
  critical: 0
  warning: 0
  info: 0
  total: 0
reviewer: orchestrator-inline
date: 2026-07-16
---

# Code Review — Phase 01 (Browser-Callable API + App Shell + Scenario List)

## Scope note

The `gsd-code-reviewer` agent run at `standard` depth over the 32 authored source
files was **interrupted by a monthly spend-limit API error before it wrote any
findings**. Rather than re-spawn it immediately (advisory, non-blocking, and at
risk of re-hitting the limit), the orchestrator performed a **focused inline
review of the security-sensitive surfaces** the phase threat models flagged
(T-1-SC, T-1-02, T-1-05), plus per-file spot-checks that were already run during
each wave merge. A full-depth agent review of the remaining files is deferred and
can be run later with `/gsd-code-review 01`.

## Inline security review (no issues found)

| Surface | File(s) | Threat | Result |
|---------|---------|--------|--------|
| CORS allow-list | `backend/settings.py`, `backend/api/main.py` | BE-01 / open-CORS | PASS — explicit origin allow-list (no `*` wildcard); `allow_credentials` left False (correct under D-02 no-auth); methods restricted to GET/POST; empty `CORS_ORIGINS=""` locks down rather than silently falling back to dev defaults. |
| Error-detail leakage | `frontend/src/components/layout/ErrorBanner.tsx`, `RootErrorBoundary.tsx` | T-1-02 (info disclosure) | PASS — both accept the error only to `console.error()`; neither renders the error's message/stack/detail to JSX. Fixed non-diagnostic user copy. |
| API base URL / secrets | `frontend/src/lib/env.ts` | T-1-05 / config drift | PASS — single typed accessor; fails loud on missing `VITE_API_BASE_URL` instead of a silent `localhost:8000` fallback (the anti-drift design working); no secret transits (D-02). |
| Supply chain | `frontend/package.json` | T-1-SC / T-1-SC-b | PASS — `msw` (`[SLOP]`) absent; only the human-approved `[SUS]` packages plus OK-verdict deps installed. |

## Deferred (not re-reviewed inline)

Full standard-depth review of the ~27 remaining non-security files (route
components, hooks, ScenarioTable/CreateScenarioDialog, tests, vite config) was not
completed by the agent. These were spot-checked during merge (typed-client usage,
no raw fetch, no hand-authored payload types, react-query invalidation, test
coverage) and the full suite passes (58 frontend + 137 backend tests, `tsc -b`
clean, build clean), but a dedicated bug-focused pass is outstanding.

**To complete:** `/gsd-code-review 01`
